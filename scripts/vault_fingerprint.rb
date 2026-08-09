#!/usr/bin/env ruby
# frozen_string_literal: true
#
# vault_fingerprint.rb — corruption detector for risky bulk operations on a vault.
#
#   capture: ruby scripts/vault_fingerprint.rb capture <vault> <out.json>
#   compare: ruby scripts/vault_fingerprint.rb compare <before.json> <after.json>
#   anchor:  ruby scripts/vault_fingerprint.rb anchor <tree_pre> <tree_post> <expect.json>
#
# Exit 0 means "no difference". ANY difference — including a pure addition — exits 1.
#
# ---------------------------------------------------------------------------------------
# DEFECTS FOUND BY ADVERSARIAL REVIEW OF v1 (2026-08-09). Each fix is non-obvious enough
# that a future edit could undo it, so the reason is recorded next to it.
#
#   D1  `clean` omitted additions, so a leftover `.orig`/`.rej` or a duplicated page —
#       the likeliest artifacts of a merge — printed "RESULT: IDENTICAL" and exited 0
#       while the line above read "pages +1". Additions are now part of `clean?`.
#   D2  `h[k] || h[k.to_sym]` collapsed `false` and `nil` onto the same sentinel, so
#       `published: false -> null` was invisible. Now a key-presence lookup.
#   D3  Non-String YAML keys (`2026: alpha`) stringified for iteration then missed both
#       lookups, hashing as `n:`. Field ids now carry the key's CLASS as well as its text.
#   D4  `raw_fm_sha256` was compared only inside the PARSE_ERROR branch — captured and
#       never read for the ~92% of pages that parse. Now compared for every page, and
#       reported as its own line when the field diff sees nothing.
#   D5  That branch was unreachable anyway: the degeneracy check raised before the
#       manifest was written. Blind spots now WARN and still write.
#   D6  `anchor` asserted nothing and exited 0 even on a wiped vault. It reported 180
#       against a git-documented 186 — the 6-page gap being blind pages — and the
#       reconciliation `observed + blind == expected` lived in a human's head. It is now
#       in code, against a stored expectation the tool cannot influence, and it exits 1.
#   D7  Invalid UTF-8 crashed the whole run, unhandled, without naming the file.
#   D9  A parse error was labelled "measurement may be reading itself" — the wrong
#       diagnosis for the damage class the tool exists to find.
#   D10 `.git` skipping was root-anchored only.
#
#   LINK BLINDNESS (the one that mattered most). v1 had no link awareness at all.
#   Mangling 1,227 wikilinks across 40 pages left lint at `warn` with `broken_links: 0`
#   and produced only "BODY: 41 pages" here — indistinguishable from the 181-187 pages a
#   real migration changes by design. Destroying links made the link-damage metric go
#   DOWN. The link graph is what makes this a wiki rather than a folder of text, so it is
#   now a first-class signal: per-page link sets, a total count, and an explicit
#   links_removed report that `clean?` refuses to ignore.
#
# PORTABILITY: stock macOS Ruby 2.6, no gems. Verify `ruby` exists before relying on this
# elsewhere; neither Python interpreter here has a YAML library.
# ---------------------------------------------------------------------------------------

require 'digest'
require 'json'
require 'date'
require 'time'   # Time#iso8601 lives here, NOT in 'date'
require 'yaml'

SKIP_TREE = %w[.git].freeze
# Churn that is never evidence of damage. Keeps the noise floor at zero on a clean
# pre/post pair, so the operator does not learn to ignore the report.
IGNORE = [%r{(\A|/)\.DS_Store\z}, %r{(\A|/)\.obsidian/workspace(-mobile)?\.json\z},
          %r{(\A|/)\.ruff_cache/}].freeze
PARSE_ERROR = 'PARSE_ERROR'
ENCODING_ERROR = 'ENCODING_ERROR'
NO_FRONTMATTER = 'NO_FRONTMATTER'
BLIND = [PARSE_ERROR, ENCODING_ERROR].freeze

# Mirrors obsidian_wiki/lint.py `_WIKILINK_RE`: target excludes `[` so a footnote-wrapped
# `^[[[page|alias]]]` yields `page`; the optional `\\?` handles pipes escaped for Markdown
# tables (`[[page\|Alias]]`), which otherwise capture as `page\`.
WIKILINK_RE = /\[\[([^\]|#\[]+?)(?:\\?[|#][^\]]*?)?\]\]/.freeze

def ignored?(rel)
  IGNORE.any? { |re| rel =~ re }
end

# D2/D3: key presence, and never coerce the key to look it up.
def fetch_key(hash, key)
  return hash[key] if hash.key?(key)
  sym = key.respond_to?(:to_sym) ? key.to_sym : nil
  return hash[sym] if sym && hash.key?(sym)
  hash[key.to_s]
end

def field_id(key)
  "#{key.class}/#{key}"
end

def canon(value)
  case value
  when nil         then 'n:'
  when true, false then "b:#{value}"
  when Integer     then "i:#{value}"
  when Float       then "f:#{value}"
  when Date        then "d:#{value.iso8601}"
  when Time        then "t:#{value.utc.iso8601}"
  when Array       then 'a:[' + value.map { |v| canon(v) }.join(',') + ']'
  when Hash
    'h:{' + value.keys.sort_by(&:to_s).map { |k|
      "#{field_id(k)}=>#{canon(fetch_key(value, k))}" }.join(',') + '}'
  else 's:' + value.to_s
  end
end

def sha(str)
  Digest::SHA256.hexdigest(str)
end

def split_page(text)
  m = text.match(/\A---\n(.*?)\n---\n?/m)
  return [nil, text] unless m
  [m[1], m.post_match]
end

def git_state(vault)
  return nil unless File.directory?(File.join(vault, '.git'))
  head = `git -C #{vault.inspect} rev-parse HEAD 2>/dev/null`.strip
  refs = `git -C #{vault.inspect} show-ref 2>/dev/null`.strip
  status = `git -C #{vault.inspect} status --porcelain 2>/dev/null`.strip
  return nil if head.empty?
  { 'head' => head, 'refs_sha256' => sha(refs), 'dirty_lines' => status.lines.size }
rescue StandardError
  nil
end

def capture(vault)
  vault = File.expand_path(vault)
  pages = {}
  tree  = {}

  Dir.glob('**/*', File::FNM_DOTMATCH, base: vault).sort.each do |rel|
    next if rel == '.' || rel == '..' || File.basename(rel) == '.'
    # D10: match a `.git` at any depth, not only at the root.
    next if SKIP_TREE.any? { |d| rel == d || rel.start_with?("#{d}/") || rel.include?("/#{d}/") || rel.end_with?("/#{d}") }
    next if ignored?(rel)
    abs = File.join(vault, rel)

    if File.symlink?(abs)
      tree[rel] = { 'type' => 'symlink', 'target' => File.readlink(abs) }
      next
    elsif File.directory?(abs)
      tree[rel] = { 'type' => 'dir' }
      next
    end
    st = File.stat(abs)
    bytes = File.binread(abs)
    tree[rel] = { 'type' => 'file', 'size' => st.size, 'uid' => st.uid, 'gid' => st.gid,
                  'mode' => format('%o', st.mode & 0o7777), 'sha256' => sha(bytes) }
    next unless rel.end_with?('.md')

    entry = {}
    begin
      text = bytes.dup.force_encoding('UTF-8')
      raise ArgumentError, 'invalid UTF-8 byte sequence' unless text.valid_encoding?
      fm, body = split_page(text)
      entry['body_sha256'] = sha(body.to_s)
      # LINK GRAPH: a sorted multiset of targets, plus the count. Both are needed —
      # the count catches wholesale destruction, the set catches a swap that preserves it.
      #
      # BODY ONLY, deliberately. Frontmatter also carries wikilinks (`relationships:` →
      # `target: "[[page]]"`), but those are already covered exactly by the field hash.
      # Scanning the whole file double-counts them AND imports frontmatter representation
      # noise: a lossless YAML round-trip re-quotes such a target, the regex stops
      # matching, and the link count drops by one with nothing actually broken. Measured
      # on this vault — that false positive is why this is scoped to the body.
      links = body.to_s.scan(WIKILINK_RE).flatten.map(&:strip).reject(&:empty?).sort
      entry['links'] = links
      entry['link_count'] = links.size
      if fm.nil?
        entry['parse_status'] = NO_FRONTMATTER
        entry['raw_fm_sha256'] = ''
        entry['fields'] = {}
      else
        entry['raw_fm_sha256'] = sha(fm)
        begin
          parsed = YAML.safe_load(fm, permitted_classes: [Date, Time], aliases: false)
          parsed = {} unless parsed.is_a?(Hash)
          entry['parse_status'] = 'ok'
          fields = {}
          parsed.keys.sort_by(&:to_s).each { |k| fields[field_id(k)] = sha(canon(fetch_key(parsed, k))) }
          entry['fields'] = fields
        rescue Psych::SyntaxError => e
          # Narrow ON PURPOSE. A broad `rescue StandardError` relabels bugs in THIS script
          # as "the vault's YAML is bad" — a defect laundered into a benign category,
          # which is the exact failure this tool exists to catch.
          entry['parse_status'] = PARSE_ERROR
          entry['parse_error'] = e.message.split("\n").first
          entry['fields'] = {}
        end
      end
    rescue ArgumentError => e
      # D7: an unreadable page is a per-page status, not a crash that kills the run.
      entry['parse_status'] = ENCODING_ERROR
      entry['parse_error'] = "#{rel}: #{e.message}"
      entry['body_sha256'] = sha(bytes)
      entry['raw_fm_sha256'] = ''
      entry['fields'] = {}
      entry['links'] = []
      entry['link_count'] = 0
    end
    pages[rel] = entry
  end

  blind = pages.select { |_, v| BLIND.include?(v['parse_status']) }
  { 'vault' => vault, 'pages' => pages, 'tree' => tree, 'git' => git_state(vault),
    'blind_spots' => blind.map { |k, v| { 'page' => k, 'status' => v['parse_status'], 'error' => v['parse_error'] } },
    'stats' => { 'pages' => pages.size, 'tree_entries' => tree.size,
                 'parse_ok' => pages.count { |_, v| v['parse_status'] == 'ok' },
                 'blind' => blind.size,
                 'no_frontmatter' => pages.count { |_, v| v['parse_status'] == NO_FRONTMATTER },
                 'link_total' => pages.values.map { |v| v['link_count'].to_i }.sum } }
end

# D5/D9: only TRUE saturation raises — unrelated pages collapsing onto one value, which
# means the instrument is reading itself. A blind page is the damage class we are hunting,
# so it warns and the manifest is still written; refusing to write is the failure mode
# that gets a guard switched off mid-operation.
def degeneracy_errors(man)
  pages = man['pages']
  return [] if pages.size < 10
  errs = []
  by_body = Hash.new(0)
  pages.each_value { |v| by_body[v['body_sha256']] += 1 }
  top_body, n_body = by_body.max_by { |_, n| n }
  errs << "#{n_body} pages share body hash #{top_body[0, 12]} — hashing a constant?" if n_body > [3, pages.size * 0.02].max
  by_field = Hash.new { |h, k| h[k] = Hash.new(0) }
  pages.each_value { |v| v['fields'].each { |k, h| by_field[k][h] += 1 } }
  by_field.each do |field, hist|
    present = hist.values.sum
    next if present < pages.size * 0.5 || present <= 10
    top, n = hist.max_by { |_, c| c }
    errs << "field #{field} has one value across all #{present} pages (#{top[0, 8]})" if n == present
  end
  errs
end

def compare(before, after)
  bp = before['pages']
  ap = after['pages']
  added   = (ap.keys - bp.keys).sort
  removed = (bp.keys - ap.keys).sort
  common  = (bp.keys & ap.keys).sort

  fa = Hash.new(0)
  fr = Hash.new(0)
  fc = Hash.new(0)
  body_changed = []
  raw_only = []
  links_removed = []
  links_added = []
  blind_either = []
  no_fm_either = []

  common.each do |rel|
    b = bp[rel]
    a = ap[rel]
    body_changed << rel if b['body_sha256'] != a['body_sha256']

    lb = (b['links'] || []).sort
    la = (a['links'] || []).sort
    lost = lb - la
    gained = la - lb
    links_removed << { 'page' => rel, 'lost' => lost.first(10), 'n' => lost.size } unless lost.empty?
    links_added << { 'page' => rel, 'n' => gained.size } unless gained.empty?

    # D4: compared for EVERY page, not only unparseable ones.
    raw_changed = b['raw_fm_sha256'] != a['raw_fm_sha256']
    if BLIND.include?(b['parse_status']) || BLIND.include?(a['parse_status'])
      blind_either << rel
      raw_only << rel if raw_changed
      next
    end
    if b['parse_status'] != 'ok' || a['parse_status'] != 'ok'
      no_fm_either << rel
      raw_only << rel if raw_changed
      next
    end
    gone = (b['fields'].keys - a['fields'].keys)
    new  = (a['fields'].keys - b['fields'].keys)
    chg  = (b['fields'].keys & a['fields'].keys).select { |k| b['fields'][k] != a['fields'][k] }
    new.each  { |k| fa[k] += 1 }
    gone.each { |k| fr[k] += 1 }
    chg.each  { |k| fc[k] += 1 }
    raw_only << rel if raw_changed && chg.empty? && gone.empty? && new.empty?
  end

  bt = before['tree']
  at = after['tree']
  { 'pages_added' => added, 'pages_removed' => removed,
    'fields_added' => fa.sort_by { |_, n| -n }.to_h,
    'fields_removed' => fr.sort_by { |_, n| -n }.to_h,
    'fields_changed' => fc.sort_by { |_, n| -n }.to_h,
    'body_changed' => body_changed,
    'links_removed' => links_removed, 'links_added' => links_added,
    'link_total_before' => before['stats']['link_total'],
    'link_total_after' => after['stats']['link_total'],
    'raw_fm_changed_fields_same' => raw_only,
    'blind_either_side' => blind_either,
    'no_frontmatter_either_side' => no_fm_either,
    'git_before' => before['git'], 'git_after' => after['git'],
    'tree_added' => (at.keys - bt.keys).sort,
    'tree_removed' => (bt.keys - at.keys).sort,
    'tree_changed' => (bt.keys & at.keys).reject { |k| bt[k] == at[k] }.sort }
end

# D1: additions count. A merge that only ADDS files is still a difference.
def clean?(d)
  d['pages_added'].empty? && d['pages_removed'].empty? &&
    d['tree_added'].empty? && d['tree_removed'].empty? && d['tree_changed'].empty? &&
    d['fields_added'].empty? && d['fields_removed'].empty? && d['fields_changed'].empty? &&
    d['body_changed'].empty? && d['raw_fm_changed_fields_same'].empty? &&
    d['links_removed'].empty? && d['links_added'].empty? &&
    d['link_total_before'] == d['link_total_after'] &&
    d['git_before'] == d['git_after']
end

def render(d, cap: 20)
  o = []
  o << "pages  +#{d['pages_added'].size} / -#{d['pages_removed'].size}"
  o << "tree   +#{d['tree_added'].size} / -#{d['tree_removed'].size} / ~#{d['tree_changed'].size}"
  { 'fields_added' => 'ADDED  ', 'fields_removed' => 'REMOVED', 'fields_changed' => 'CHANGED' }
    .each { |k, l| o << "#{l}: " + (d[k].empty? ? '(none)' : d[k].map { |f, n| "#{f}=#{n}" }.join('  ')) }
  o << "BODY   : #{d['body_changed'].size} page(s)"
  lost = d['links_removed'].map { |x| x['n'] }.sum
  o << "LINKS  : #{d['link_total_before']} -> #{d['link_total_after']}" \
       "  (#{lost} removed across #{d['links_removed'].size} page(s))"
  o << "RAW-FM changed, fields identical: #{d['raw_fm_changed_fields_same'].size}"
  o << "BLIND (parse/encoding error either side): #{d['blind_either_side'].size} <- fields unchecked"
  o << "NO-FRONTMATTER (benign, body-hashed): #{d['no_frontmatter_either_side'].size}"
  o << "GIT    : #{d['git_before'] == d['git_after'] ? 'unchanged' : "CHANGED #{d['git_before'].inspect} -> #{d['git_after'].inspect}"}"
  d['links_removed'].first(cap).each { |x| o << "  LINKS LOST: #{x['page']} (-#{x['n']}) #{x['lost'].join(', ')}" }
  { 'pages_removed' => 'REMOVED PAGE', 'pages_added' => 'ADDED PAGE', 'tree_removed' => 'REMOVED FILE',
    'tree_added' => 'ADDED FILE', 'tree_changed' => 'CHANGED FILE', 'body_changed' => 'CHANGED BODY',
    'raw_fm_changed_fields_same' => 'RAW-FM ONLY', 'blind_either_side' => 'BLIND' }.each do |k, l|
    d[k].first(cap).each { |p| o << "  #{l}: #{p}" }
    o << "  #{l}: ... and #{d[k].size - cap} more" if d[k].size > cap
  end
  o.join("\n")
end

cmd = ARGV.shift
case cmd
when 'capture'
  vault, out = ARGV
  abort 'usage: capture <vault> <out.json>' unless vault && out
  man = capture(vault)
  errs = degeneracy_errors(man)
  abort("DEGENERACY CHECK FAILED (measurement may be reading itself):\n  - " + errs.join("\n  - ")) unless errs.empty?
  File.write(out, JSON.pretty_generate(man))
  warn "captured #{man['stats'].to_json} -> #{out}"
  unless man['blind_spots'].empty?
    warn "WARNING: #{man['blind_spots'].size} page(s) BLIND to the field diff (parse/encoding error)."
    warn '         Manifest written; these are covered only by raw-frontmatter, body and link hashes:'
    man['blind_spots'].first(20).each { |b| warn "  #{b['status']}  #{b['page']}" }
  end
when 'compare'
  a, b = ARGV
  abort 'usage: compare <before.json> <after.json>' unless a && b
  d = compare(JSON.parse(File.read(a)), JSON.parse(File.read(b)))
  puts render(d)
  ok = clean?(d)
  puts(ok ? "\nRESULT: IDENTICAL" : "\nRESULT: DIFFERENCES PRESENT")
  exit(ok ? 0 : 1)
when 'anchor'
  # D6: a known-answer test asserts against an expectation established OUTSIDE this tool
  # (git history, commit messages, an independent count) and EXITS NON-ZERO on mismatch.
  # Printing a diff and exiting 0 is not a known-answer test.
  pre, post, expect = ARGV
  abort 'usage: anchor <tree_pre> <tree_post> <expect.json>' unless pre && post && expect
  d = compare(capture(pre), capture(post))
  puts render(d)
  exp = JSON.parse(File.read(expect))
  blind = d['blind_either_side'].size
  fails = []
  (exp['fields_added'] || {}).each do |field, want|
    got = d['fields_added'][field] || 0
    # A blind page's delta is UNKNOWN, not "definitely one". `observed + blind == expected`
    # was the obvious formula and it is wrong: it assumes every blind page gained the
    # field, which holds for a field added to nearly every page and fails for one that
    # changed on nobody (tier over this range: 0 observed, 6 blind, 0 expected). The
    # honest assertion is the interval the evidence actually supports.
    lo = got
    hi = got + blind
    unless want.between?(lo, hi)
      fails << "fields_added[#{field}]: expected #{want}, supported interval is [#{lo}, #{hi}] " \
               "(#{got} observed, #{blind} blind/unattributable)"
    end
  end
  { 'pages_added' => d['pages_added'].size, 'pages_removed' => d['pages_removed'].size,
    'blind' => blind }.each do |k, got|
    fails << "#{k}: got #{got}, expected #{exp[k]}" if exp.key?(k) && got != exp[k]
  end
  if fails.empty?
    puts "\nANCHOR: PASS — #{exp.fetch('note', 'expectations met')}"
    exit 0
  end
  puts "\nANCHOR: FAIL"
  fails.each { |f| puts "  - #{f}" }
  exit 1
else
  abort 'usage: vault_fingerprint.rb {capture|compare|anchor} ...'
end
