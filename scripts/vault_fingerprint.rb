#!/usr/bin/env ruby
# frozen_string_literal: true
#
# vault_fingerprint.rb — corruption detector for risky bulk operations on a vault.
#
#   capture:  ruby scripts/vault_fingerprint.rb capture <vault> <out.json>
#   compare:  ruby scripts/vault_fingerprint.rb compare <before.json> <after.json>
#   anchor:   ruby scripts/vault_fingerprint.rb anchor  <tree_pre> <tree_post>
#
# WHY THIS SHAPE (each choice was measured, not assumed — 2026-08-09 adversarial pass):
#
#   * Path-keyed, never a sorted multiset. An unkeyed manifest makes a frontmatter SWAP
#     between two pages and a page RENAME both invisible.
#   * Values are TYPE-TAGGED. `key=str(value)` cannot see `tags: [a,b]` -> "a, b" or
#     `0.42` -> "0.42"; the latter breaks float() in trust._parse_confidence.
#   * BOTH a parsed hash and a raw hash are kept. A raw hash alone false-positives on
#     ~99% of pages after a lossless YAML round-trip (the most likely thing a migration
#     does). A parsed hash alone is blind to pages whose frontmatter is not valid YAML —
#     and this vault's own schema migration rewrote exactly those, unseen.
#   * BODIES are hashed. Frontmatter is ~5% of vault bytes; ~99.6% of wikilinks live in
#     bodies.
#   * The whole tree is inventoried, INCLUDING gitignored paths. `_raw/` is gitignored,
#     untracked, and skipped by lint and trust-check — the least protected data present.
#   * Reports are FIELD-LEVEL. A real migration changes 88-91% of pages by design; a
#     page-level diff is an unreadable wall that trains the operator to ignore it.
#   * Degeneracy RAISES rather than warns. If unrelated pages collapse onto one
#     fingerprint value, the instrument is reading itself.
#
# PORTABILITY: stock macOS Ruby, no gems. The Ubuntu devbox needs `ruby` installed, or a
# Python port with PyYAML — neither interpreter here has a YAML library.

require 'digest'
require 'json'
require 'date'
require 'time'   # Time#iso8601 lives here, NOT in 'date'
require 'yaml'
require 'set'

SKIP_TREE = %w[.git].freeze
PARSE_ERROR = 'PARSE_ERROR'
NO_FRONTMATTER = 'NO_FRONTMATTER'

# --- canonical, type-tagged rendering -------------------------------------------------

def canon(value)
  case value
  when nil        then 'n:'
  when true, false then "b:#{value}"
  when Integer    then "i:#{value}"
  when Float      then "f:#{value}"
  when Date       then "d:#{value.iso8601}"
  when Time       then "t:#{value.utc.iso8601}"
  when Array      then 'a:[' + value.map { |v| canon(v) }.join(',') + ']'
  when Hash       then 'h:{' + value.keys.map(&:to_s).sort.map { |k|
                         "#{k}=>#{canon(value[k] || value[k.to_sym])}" }.join(',') + '}'
  else                 's:' + value.to_s
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

# --- capture --------------------------------------------------------------------------

def capture(vault)
  vault = File.expand_path(vault)
  pages = {}
  tree  = {}

  Dir.glob('**/*', File::FNM_DOTMATCH, base: vault).sort.each do |rel|
    next if rel == '.' || rel == '..'
    next if SKIP_TREE.any? { |d| rel == d || rel.start_with?("#{d}/") }
    abs = File.join(vault, rel)

    # Outer envelope: every file, including gitignored ones.
    if File.symlink?(abs)
      tree[rel] = { 'type' => 'symlink', 'target' => File.readlink(abs) }
      next
    elsif File.directory?(abs)
      tree[rel] = { 'type' => 'dir' }
      next
    end
    st = File.stat(abs)
    bytes = File.binread(abs)
    tree[rel] = { 'type' => 'file', 'size' => st.size,
                  'mode' => format('%o', st.mode & 0o7777), 'sha256' => sha(bytes) }

    next unless rel.end_with?('.md')

    text = bytes.force_encoding('UTF-8')
    fm, body = split_page(text)
    entry = { 'body_sha256' => sha(body.to_s) }
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
        entry['fields'] = parsed.keys.map(&:to_s).sort.to_h { |k|
          [k, sha(canon(parsed[k] || parsed[k.to_sym]))]
        }
      rescue StandardError => e
        entry['parse_status'] = PARSE_ERROR
        entry['parse_error'] = e.message.split("\n").first
        entry['fields'] = {}
      end
    end
    pages[rel] = entry
  end

  { 'vault' => vault, 'pages' => pages, 'tree' => tree,
    'stats' => { 'pages' => pages.size, 'tree_entries' => tree.size,
                 'parse_ok' => pages.count { |_, v| v['parse_status'] == 'ok' },
                 'parse_error' => pages.count { |_, v| v['parse_status'] == PARSE_ERROR },
                 'no_frontmatter' => pages.count { |_, v| v['parse_status'] == NO_FRONTMATTER } } }
end

# --- degeneracy: the instrument must not be reading itself -----------------------------

def assert_not_degenerate!(man)
  pages = man['pages']
  return if pages.size < 10 # saturation is meaningless on a tiny sample

  errs = []
  bad = man['stats']['parse_error']
  errs << "#{bad} page(s) failed YAML parse; type-tagged comparison is blind to them" if bad.positive?

  # Unrelated pages collapsing onto one body hash means we are hashing a constant.
  by_body = Hash.new(0)
  pages.each_value { |v| by_body[v['body_sha256']] += 1 }
  top_body, n_body = by_body.max_by { |_, n| n }
  if n_body > [3, pages.size * 0.02].max
    errs << "#{n_body} pages share body hash #{top_body[0, 12]} — hashing a constant?"
  end

  # A field whose value-hash is identical across nearly every page is not discriminating.
  by_field = Hash.new { |h, k| h[k] = Hash.new(0) }
  pages.each_value { |v| v['fields'].each { |k, h| by_field[k][h] += 1 } }
  by_field.each do |field, hist|
    present = hist.values.sum
    next if present < pages.size * 0.5
    top, n = hist.max_by { |_, c| c }
    next unless n == present && present > 10
    errs << "field #{field.inspect} has one value across all #{present} pages (#{top[0, 8]})"
  end

  return if errs.empty?
  raise "DEGENERACY CHECK FAILED (measurement may be reading itself):\n  - " + errs.join("\n  - ")
end

# --- compare: field-level, not page-level ---------------------------------------------

def compare(before, after)
  bp, ap = before['pages'], after['pages']
  added   = (ap.keys - bp.keys).sort
  removed = (bp.keys - ap.keys).sort
  common  = (bp.keys & ap.keys).sort

  fields_added = Hash.new(0)
  fields_removed = Hash.new(0)
  fields_changed = Hash.new(0)
  body_changed = []
  raw_only_changed = []
  parse_error_either = []
  no_frontmatter_either = []

  common.each do |rel|
    b, a = bp[rel], ap[rel]
    body_changed << rel if b['body_sha256'] != a['body_sha256']
    if b['parse_status'] != 'ok' || a['parse_status'] != 'ok'
      # These two are NOT the same thing and must never be summed. PARSE_ERROR is a
      # genuine blind spot: frontmatter exists, carries fields, and the field diff cannot
      # see them. NO_FRONTMATTER is a legitimate state with no fields to compare, and the
      # body hash still covers the file completely. Conflating them inflates the reported
      # blind spot and buries the real one.
      if b['parse_status'] == PARSE_ERROR || a['parse_status'] == PARSE_ERROR
        parse_error_either << rel
        raw_only_changed << rel if b['raw_fm_sha256'] != a['raw_fm_sha256']
      else
        no_frontmatter_either << rel
      end
      next
    end
    (a['fields'].keys - b['fields'].keys).each { |k| fields_added[k] += 1 }
    (b['fields'].keys - a['fields'].keys).each { |k| fields_removed[k] += 1 }
    (b['fields'].keys & a['fields'].keys).each do |k|
      fields_changed[k] += 1 if b['fields'][k] != a['fields'][k]
    end
  end

  bt, at = before['tree'], after['tree']
  tree_added   = (at.keys - bt.keys).sort
  tree_removed = (bt.keys - at.keys).sort
  tree_changed = (bt.keys & at.keys).reject { |k| bt[k] == at[k] }.sort

  { 'pages_added' => added, 'pages_removed' => removed,
    'fields_added' => fields_added.sort_by { |_, n| -n }.to_h,
    'fields_removed' => fields_removed.sort_by { |_, n| -n }.to_h,
    'fields_changed' => fields_changed.sort_by { |_, n| -n }.to_h,
    'body_changed' => body_changed,
    'raw_fm_changed_on_parse_error' => raw_only_changed,
    'parse_error_either_side' => parse_error_either,
    'no_frontmatter_either_side' => no_frontmatter_either,
    'tree_added' => tree_added, 'tree_removed' => tree_removed,
    'tree_changed' => tree_changed }
end

def render(d)
  out = []
  out << "pages  +#{d['pages_added'].size} / -#{d['pages_removed'].size}"
  out << "tree   +#{d['tree_added'].size} / -#{d['tree_removed'].size} / ~#{d['tree_changed'].size}"
  %w[fields_added fields_removed fields_changed].each do |k|
    label = k.split('_').last.upcase.ljust(7)
    v = d[k]
    out << "#{label}: " + (v.empty? ? '(none)' : v.map { |f, n| "#{f}=#{n}" }.join('  '))
  end
  out << "BODY   : #{d['body_changed'].size} page(s)"
  out << "PARSE-ERROR (real blind spot): #{d['parse_error_either_side'].size}" \
         " (raw-hash changed on #{d['raw_fm_changed_on_parse_error'].size}) <- fields unchecked"
  out << "NO-FRONTMATTER (benign, body-hashed): #{d['no_frontmatter_either_side'].size}"
  d['pages_removed'].first(20).each { |p| out << "  REMOVED PAGE: #{p}" }
  d['tree_removed'].first(20).each { |p| out << "  REMOVED FILE: #{p}" }
  out.join("\n")
end

# --- main -----------------------------------------------------------------------------

cmd = ARGV.shift
case cmd
when 'capture'
  vault, out = ARGV
  abort 'usage: capture <vault> <out.json>' unless vault && out
  man = capture(vault)
  assert_not_degenerate!(man)
  File.write(out, JSON.pretty_generate(man))
  warn "captured #{man['stats'].to_json} -> #{out}"
when 'compare'
  a, b = ARGV
  abort 'usage: compare <before.json> <after.json>' unless a && b
  d = compare(JSON.parse(File.read(a)), JSON.parse(File.read(b)))
  puts render(d)
  clean = d['pages_removed'].empty? && d['tree_removed'].empty? &&
          d['fields_added'].empty? && d['fields_removed'].empty? &&
          d['fields_changed'].empty? && d['body_changed'].empty? &&
          d['tree_changed'].empty? && d['raw_fm_changed_on_parse_error'].empty?
  puts(clean ? "\nRESULT: IDENTICAL" : "\nRESULT: DIFFERENCES PRESENT")
  exit(clean ? 0 : 1)
when 'anchor'
  # Known-answer test: run across a migration whose effect is known independently.
  pre, post = ARGV
  abort 'usage: anchor <tree_pre> <tree_post>' unless pre && post
  d = compare(capture(pre), capture(post))
  puts render(d)
else
  abort 'usage: vault_fingerprint.rb {capture|compare|anchor} ...'
end
