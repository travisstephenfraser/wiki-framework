const fs = require('fs');
const path = require('path');

const VAULT_ROOT = 'C:/Users/tfras/projects/.vault';
const ARCHIVES_DIR = path.join(VAULT_ROOT, '_archives');
const META_DIR = path.join(VAULT_ROOT, '_meta');

// Helper to recursively list markdown files
function getMdFiles(dir) {
  let results = [];
  const list = fs.readdirSync(dir);
  list.forEach(file => {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);
    if (stat && stat.isDirectory()) {
      // Skip _archives, _meta, .git, .obsidian, and nested obsidian-wiki codebase
      if (file !== '_archives' && file !== '_meta' && file !== '.git' && file !== '.obsidian' && file !== 'obsidian-wiki') {
        results = results.concat(getMdFiles(filePath));
      }
    } else if (file.endsWith('.md')) {
      results.push(filePath);
    }
  });
  return results;
}

// 1. Scan all md files
console.log("Scanning files...");
const mdFiles = getMdFiles(VAULT_ROOT);
console.log(`Found ${mdFiles.length} markdown files.`);

const pages = {};
const allFilesSet = new Set();
const basenameToPath = {};
const aliasToPath = {};

// Basic frontmatter parser
function parseFrontmatter(content) {
  const lines = content.split('\n');
  if (lines[0].trim() !== '---') return { fm: {}, body: content };
  
  let fmText = '';
  let bodyStartLine = 1;
  for (let i = 1; i < lines.length; i++) {
    if (lines[i].trim() === '---') {
      bodyStartLine = i + 1;
      break;
    }
    fmText += lines[i] + '\n';
  }
  
  const bodyText = lines.slice(bodyStartLine).join('\n');
  const fm = {};
  
  // Simple yaml-like parser
  const fmLines = fmText.split('\n');
  let currentKey = null;
  let inList = false;
  
  fmLines.forEach(line => {
    const trimmed = line.trim();
    if (!trimmed) return;
    
    // Check list item
    if (trimmed.startsWith('-')) {
      if (currentKey && Array.isArray(fm[currentKey])) {
        let val = trimmed.substring(1).trim();
        // Remove outer quotes if any
        if (val.startsWith('"') && val.endsWith('"')) val = val.slice(1, -1);
        if (val.startsWith("'") && val.endsWith("'")) val = val.slice(1, -1);
        fm[currentKey].push(val);
      }
      return;
    }
    
    const colonIdx = line.indexOf(':');
    if (colonIdx === -1) return;
    
    const key = line.substring(0, colonIdx).trim();
    let val = line.substring(colonIdx + 1).trim();
    
    // Check if inline list like [a, b, c]
    if (val.startsWith('[') && val.endsWith(']')) {
      const items = val.slice(1, -1).split(',').map(x => {
        let s = x.trim();
        if (s.startsWith('"') && s.endsWith('"')) s = s.slice(1, -1);
        if (s.startsWith("'") && s.endsWith("'")) s = s.slice(1, -1);
        return s;
      }).filter(Boolean);
      fm[key] = items;
      currentKey = key;
    } else if (val === '') {
      fm[key] = [];
      currentKey = key;
    } else {
      if (val.startsWith('"') && val.endsWith('"')) val = val.slice(1, -1);
      if (val.startsWith("'") && val.endsWith("'")) val = val.slice(1, -1);
      fm[key] = val;
      currentKey = key;
    }
  });
  
  // Nested fields like provenance
  // e.g. provenance:
  //        extracted: 0.72
  // Let's parse nested fields by matching indented lines after provenance:
  const provMatch = fmText.match(/provenance:\s*\n(\s+extracted:\s*\S+\n)?(\s+inferred:\s*\S+\n)?(\s+ambiguous:\s*\S+\n)?/);
  if (provMatch) {
    const prov = {};
    const extM = fmText.match(/\s+extracted:\s*(\S+)/);
    const infM = fmText.match(/\s+inferred:\s*(\S+)/);
    const ambM = fmText.match(/\s+ambiguous:\s*(\S+)/);
    if (extM) prov.extracted = parseFloat(extM[1]);
    if (infM) prov.inferred = parseFloat(infM[1]);
    if (ambM) prov.ambiguous = parseFloat(ambM[1]);
    fm.provenance = prov;
  }
  
  return { fm, body: bodyText };
}

// First pass: index all files, basenames, aliases
mdFiles.forEach(file => {
  const content = fs.readFileSync(file, 'utf-8');
  const relPath = path.relative(VAULT_ROOT, file).replace(/\\/g, '/');
  allFilesSet.add(relPath);
  
  const basename = path.basename(file);
  const cleanName = basename.slice(0, -3); // remove .md
  basenameToPath[cleanName.toLowerCase()] = relPath;
  basenameToPath[basename.toLowerCase()] = relPath;
  
  const { fm, body } = parseFrontmatter(content);
  
  if (fm.aliases && Array.isArray(fm.aliases)) {
    fm.aliases.forEach(alias => {
      aliasToPath[alias.toLowerCase()] = relPath;
    });
  }
  
  pages[relPath] = {
    relPath,
    absPath: file,
    content,
    fm,
    body,
    outgoingLinks: [],
    incomingLinks: [],
    tags: Array.isArray(fm.tags) ? fm.tags : [],
    summary: fm.summary || '',
    sources: fm.sources || null,
    created: fm.created || null,
    updated: fm.updated || null,
    title: fm.title || ''
  };
});

// Helper to resolve link target
function resolveLink(target) {
  const cleanTarget = target.split('|')[0].trim().toLowerCase();
  
  // 1. Check exact relPath (with or without .md)
  let testPath = cleanTarget.endsWith('.md') ? cleanTarget : cleanTarget + '.md';
  if (allFilesSet.has(testPath)) return testPath;
  
  // 2. Check basename match
  if (basenameToPath[cleanTarget]) return basenameToPath[cleanTarget];
  
  // 3. Check alias match
  if (aliasToPath[cleanTarget]) return aliasToPath[cleanTarget];
  
  return null;
}

// Second pass: extract and resolve wikilinks
Object.keys(pages).forEach(relPath => {
  const page = pages[relPath];
  
  // Regexp for wikilinks [[link]]
  const linkRegex = /\[\[(.*?)\]\]/g;
  let match;
  while ((match = linkRegex.exec(page.content)) !== null) {
    const rawLink = match[1];
    const resolved = resolveLink(rawLink);
    page.outgoingLinks.push({
      raw: rawLink,
      resolved: resolved
    });
    
    if (resolved && resolved !== relPath) {
      pages[resolved].incomingLinks.push(relPath);
    }
  }
});

// Lint Findings Arrays
const findings = {
  orphans: [],
  brokenLinks: [],
  missingFrontmatter: [],
  missingSummary: [],
  staleContent: [],
  contradictions: [],
  indexIssues: [],
  provenanceIssues: [],
  fragmentedClusters: [],
  visibilityIssues: []
};

// 1. Orphaned Pages
Object.keys(pages).forEach(relPath => {
  if (relPath === 'index.md' || relPath === 'log.md') return;
  const page = pages[relPath];
  if (page.incomingLinks.length === 0) {
    findings.orphans.push(relPath);
  }
});

// 2. Broken Wikilinks
Object.keys(pages).forEach(relPath => {
  const page = pages[relPath];
  page.outgoingLinks.forEach(link => {
    if (!link.resolved) {
      // Find line number
      const lines = page.content.split('\n');
      let lineNum = 1;
      for (let i = 0; i < lines.length; i++) {
        if (lines[i].includes(`[[${link.raw}]]`)) {
          lineNum = i + 1;
          break;
        }
      }
      // Skip wikiexample.md which is a template and has placeholder broken links
      if (relPath.includes('wikiexample.md')) return;
      findings.brokenLinks.push(`${relPath}:${lineNum} — links to [[${link.raw}]]`);
    }
  });
});

// 3. Missing Frontmatter & Summaries
Object.keys(pages).forEach(relPath => {
  const page = pages[relPath];
  const missing = [];
  const required = ['title', 'category', 'tags', 'sources', 'created', 'updated'];
  
  required.forEach(field => {
    if (page.fm[field] === undefined || page.fm[field] === null || page.fm[field] === '') {
      missing.push(field);
    }
  });
  
  if (missing.length > 0) {
    findings.missingFrontmatter.push(`${relPath} — missing: ${missing.join(', ')}`);
  }
  
  // Summary checks (soft warnings)
  if (!page.summary) {
    findings.missingSummary.push(`${relPath} — no summary: field`);
  } else if (page.summary.length > 200) {
    findings.missingSummary.push(`${relPath} — summary exceeds 200 chars (${page.summary.length} chars)`);
  }
});

// 4. Stale Content
// We read the manifest to see file modification times and match them.
let manifest = null;
if (fs.existsSync(path.join(VAULT_ROOT, '.manifest.json'))) {
  manifest = JSON.parse(fs.readFileSync(path.join(VAULT_ROOT, '.manifest.json'), 'utf-8'));
}
if (manifest && manifest.sources) {
  Object.keys(pages).forEach(relPath => {
    const page = pages[relPath];
    // Find all sources that contributed to this page in the manifest
    let isStale = false;
    let staleDetail = '';
    
    Object.keys(manifest.sources).forEach(sourceKey => {
      const src = manifest.sources[sourceKey];
      const pagesCreatedOrUpdated = (src.pages_created || []).concat(src.pages_updated || []);
      if (pagesCreatedOrUpdated.includes(relPath)) {
        // Source modified time vs page updated time
        const srcModTime = new Date(src.modified_at || src.ingested_at);
        const pageUpdateTime = new Date(page.updated || page.created);
        
        if (srcModTime > pageUpdateTime) {
          isStale = true;
          staleDetail = `source ${sourceKey} modified ${src.modified_at}, page last updated ${page.updated}`;
        }
      }
    });
    
    if (isStale) {
      findings.staleContent.push(`${relPath} — ${staleDetail}`);
    }
  });
}

// 5. Index Consistency
// Parse index.md to extract all resolved links
const indexPage = pages['index.md'];
const indexLinks = new Set();
if (indexPage) {
  indexPage.outgoingLinks.forEach(link => {
    if (link.resolved) indexLinks.add(link.resolved);
  });
}

Object.keys(pages).forEach(relPath => {
  if (relPath === 'index.md' || relPath === 'log.md') return;
  // Index consistency check only applies to root directories, not projects!
  if (relPath.startsWith('projects/')) return;
  
  if (!indexLinks.has(relPath)) {
    findings.indexIssues.push(`${relPath} exists on disk but not in index.md`);
  }
});

// 6. Provenance & Inferences Check
// Sort pages to identify top 10 hubs
const pageList = Object.keys(pages)
  .filter(p => p !== 'index.md' && p !== 'log.md')
  .map(p => ({ relPath: p, incomingCount: pages[p].incomingLinks.length }))
  .sort((a, b) => b.incomingCount - a.incomingCount);
const top10Hubs = new Set(pageList.slice(0, 10).map(x => x.relPath));

Object.keys(pages).forEach(relPath => {
  const page = pages[relPath];
  
  // Skip synthesis/ and concepts/ if they carry a macro-level provenance declaration in frontmatter
  const isSynthesisOrConcept = relPath.startsWith('synthesis/') || relPath.startsWith('concepts/');
  const hasProvenanceFM = page.fm.provenance !== undefined && page.fm.provenance !== null;
  if (isSynthesisOrConcept && hasProvenanceFM) return;
  
  // Claim counting in body (exclude headers, empty lines, and the sources section)
  const lines = page.body.split('\n');
  let inSources = false;
  let inCodeBlock = false;
  let claimLines = [];
  
  lines.forEach(line => {
    const trimmed = line.trim();
    if (!trimmed) return;
    if (trimmed.startsWith('```')) {
      inCodeBlock = !inCodeBlock;
      return;
    }
    if (inCodeBlock) return;
    
    if (trimmed.startsWith('## Sources') || trimmed.startsWith('## Related')) {
      inSources = true;
    }
    if (trimmed.startsWith('##') && trimmed !== '## Sources' && trimmed !== '## Related') {
      inSources = false;
    }
    if (inSources) return;
    
    // Treat lists and standard non-header paragraphs as claims
    if (!trimmed.startsWith('#')) {
      claimLines.push(trimmed);
    }
  });
  
  if (claimLines.length === 0) return;
  
  let inferredCount = 0;
  let ambiguousCount = 0;
  let extractedCount = 0;
  
  claimLines.forEach(line => {
    if (line.includes('^[inferred]')) {
      inferredCount++;
    } else if (line.includes('^[ambiguous]')) {
      ambiguousCount++;
    } else {
      extractedCount++;
    }
  });
  
  const totalClaims = inferredCount + ambiguousCount + extractedCount;
  const inferredFraction = inferredCount / totalClaims;
  const ambiguousFraction = ambiguousCount / totalClaims;
  const extractedFraction = extractedCount / totalClaims;
  
  // (a) Ambiguous > 15%
  if (ambiguousFraction > 0.15) {
    findings.provenanceIssues.push(`${relPath} — AMBIGUOUS > 15%: ${(ambiguousFraction * 100).toFixed(0)}% of claims are ambiguous (re-source or move to synthesis/)`);
  }
  
  // (b) Inferred > 40% with no sources in frontmatter
  const hasSources = page.sources && page.sources.length > 0;
  if (inferredFraction > 0.40 && !hasSources) {
    findings.provenanceIssues.push(`${relPath} — unsourced synthesis: no sources: field, ${(inferredFraction * 100).toFixed(0)}% inferred`);
  }
  
  // (c) Top 10 Hub page with Inferred > 20%
  if (top10Hubs.has(relPath) && inferredFraction > 0.20) {
    findings.provenanceIssues.push(`${relPath} — hub page (${pages[relPath].incomingLinks.length} incoming links) with INFERRED=${(inferredFraction * 100).toFixed(0)}%: errors here propagate widely`);
  }
  
  // (d) Provenance Drift from frontmatter
  if (page.fm.provenance) {
    const fmExt = page.fm.provenance.extracted !== undefined ? page.fm.provenance.extracted : 1.0;
    const fmInf = page.fm.provenance.inferred !== undefined ? page.fm.provenance.inferred : 0.0;
    const fmAmb = page.fm.provenance.ambiguous !== undefined ? page.fm.provenance.ambiguous : 0.0;
    
    const driftExt = Math.abs(fmExt - extractedFraction);
    const driftInf = Math.abs(fmInf - inferredFraction);
    const driftAmb = Math.abs(fmAmb - ambiguousFraction);
    
    if (driftExt > 0.20 || driftInf > 0.20 || driftAmb > 0.20) {
      findings.provenanceIssues.push(`${relPath} — drift: frontmatter says inferred=${fmInf.toFixed(2)}, recomputed=${inferredFraction.toFixed(2)}`);
    }
  }
});

// 7. Fragmented Tag Clusters
const tagGroups = {};
Object.keys(pages).forEach(relPath => {
  const page = pages[relPath];
  page.tags.forEach(tag => {
    // Skip system tags like status/* or visibility/*
    if (tag.startsWith('status/') || tag.startsWith('visibility/')) return;
    if (!tagGroups[tag]) tagGroups[tag] = [];
    tagGroups[tag].push(relPath);
  });
});

Object.keys(tagGroups).forEach(tag => {
  const group = tagGroups[tag];
  const n = group.length;
  if (n >= 5) {
    // Count link edges between pages in the group
    let actualLinks = 0;
    const groupSet = new Set(group);
    
    // Generate all pairs
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const pA = pages[group[i]];
        const pB = pages[group[j]];
        
        const A_links_B = pA.outgoingLinks.some(l => l.resolved === pB.relPath);
        const B_links_A = pB.outgoingLinks.some(l => l.resolved === pA.relPath);
        
        if (A_links_B || B_links_A) {
          actualLinks++;
        }
      }
    }
    
    const maxPossible = (n * (n - 1)) / 2;
    const cohesion = actualLinks / maxPossible;
    
    if (cohesion < 0.15) {
      findings.fragmentedClusters.push(`**#${tag}** — ${n} pages, cohesion=${cohesion.toFixed(2)} ⚠️ — run cross-linker on this tag`);
    }
  }
});

// 8. Visibility Tag Consistency & PII Check
Object.keys(pages).forEach(relPath => {
  const page = pages[relPath];
  
  // (a) Check if page contains PII-like patterns but lacks visibility/pii or visibility/internal
  const hasVisibilityPii = page.tags.includes('visibility/pii');
  const hasVisibilityInternal = page.tags.includes('visibility/internal');
  
  if (!hasVisibilityPii && !hasVisibilityInternal) {
    // Check body for sensitive keys followed by values
    const lines = page.body.split('\n');
    let piiPatternFound = false;
    let piiDetail = '';
    
    const piiRegex = /(password|api_key|secret|token|ssn|email|phone)\s*[:=]\s*[^\s"']{3,}/i;
    // To make it smarter, check if there is email format or phone format
    const emailRegex = /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/;
    const phoneRegex = /\+?\d[\d-\s()]{7,}/;
    
    for (let line of lines) {
      if (piiRegex.test(line)) {
        // Double check to avoid normal variable references or standard config keys
        const match = line.match(piiRegex);
        const matchedKey = match[1].toLowerCase();
        
        if (matchedKey === 'email' && emailRegex.test(line)) {
          piiPatternFound = true;
          piiDetail = `contains email value pattern`;
          break;
        } else if (matchedKey === 'phone' && phoneRegex.test(line)) {
          piiPatternFound = true;
          piiDetail = `contains phone value pattern`;
          break;
        } else if (['password', 'api_key', 'secret', 'token', 'ssn'].includes(matchedKey)) {
          // Exclude lines that look like generic placeholders or env name definitions
          if (!line.includes('<') && !line.includes('YOUR_') && !line.includes('PLACEHOLDER') && !line.includes('Env:')) {
            piiPatternFound = true;
            piiDetail = `contains sensitive keyword '${matchedKey}' with value`;
            break;
          }
        }
      }
    }
    
    if (piiPatternFound) {
      findings.visibilityIssues.push(`${relPath} — ${piiDetail} but no visibility/pii tag`);
    }
  }
  
  // (b) Tagged visibility/pii but missing sources: frontmatter
  if (hasVisibilityPii && (!page.sources || page.sources.length === 0)) {
    findings.visibilityIssues.push(`${relPath} — tagged visibility/pii but missing sources: frontmatter`);
  }
});

// Check system tags in _meta/taxonomy.md
const taxonomyPath = path.join(VAULT_ROOT, '_meta/taxonomy.md');
if (fs.existsSync(taxonomyPath)) {
  const taxContent = fs.readFileSync(taxonomyPath, 'utf-8');
  // Check if visibility/public, visibility/internal, visibility/pii are registered as normal tags (under Domain or Project section)
  // Let's see if visibility/ tags are defined in the lists under Domain Tags or Project Tags or Descriptor Tags
  const lines = taxContent.split('\n');
  let inNormalSections = false;
  lines.forEach(line => {
    if (line.includes('## Domain Tags') || line.includes('## Project Tags') || line.includes('## Descriptor Tags')) {
      inNormalSections = true;
    }
    if (line.includes('## Alias Migration') || line.includes('## Reserved:')) {
      inNormalSections = false;
    }
    
    if (inNormalSections && line.includes('visibility/')) {
      findings.visibilityIssues.push(`_meta/taxonomy.md — contains visibility/ entry in regular tag lists`);
    }
  });
}

// Generate the output report
let report = `## Wiki Health Report\n\n`;

const totalIssues = Object.values(findings).reduce((acc, curr) => acc + curr.length, 0);

report += `### Summary\n- **Total files scanned:** ${mdFiles.length}\n- **Total issues found:** ${totalIssues}\n\n`;

report += `### Orphaned Pages (${findings.orphans.length} found)\n`;
if (findings.orphans.length === 0) report += `- None 🎉\n`;
else findings.orphans.forEach(o => report += `- \`${o}\` — no incoming links\n`);

report += `\n### Broken Wikilinks (${findings.brokenLinks.length} found)\n`;
if (findings.brokenLinks.length === 0) report += `- None 🎉\n`;
else findings.brokenLinks.forEach(b => report += `- \`${b}\`\n`);

report += `\n### Missing Frontmatter (${findings.missingFrontmatter.length} found)\n`;
if (findings.missingFrontmatter.length === 0) report += `- None 🎉\n`;
else findings.missingFrontmatter.forEach(m => report += `- \`${m}\`\n`);

report += `\n### Stale Content (${findings.staleContent.length} found)\n`;
if (findings.staleContent.length === 0) report += `- None 🎉\n`;
else findings.staleContent.forEach(s => report += `- \`${s}\`\n`);

report += `\n### Contradictions (${findings.contradictions.length} found)\n`;
if (findings.contradictions.length === 0) report += `- None 🎉\n`;
else findings.contradictions.forEach(c => report += `- \`${c}\`\n`);

report += `\n### Index Issues (${findings.indexIssues.length} found)\n`;
if (findings.indexIssues.length === 0) report += `- None 🎉\n`;
else findings.indexIssues.forEach(i => report += `- \`${i}\`\n`);

report += `\n### Missing Summary (${findings.missingSummary.length} found — soft)\n`;
if (findings.missingSummary.length === 0) report += `- None 🎉\n`;
else findings.missingSummary.forEach(ms => report += `- \`${ms}\`\n`);

report += `\n### Provenance Issues (${findings.provenanceIssues.length} found)\n`;
if (findings.provenanceIssues.length === 0) report += `- None 🎉\n`;
else findings.provenanceIssues.forEach(p => report += `- \`${p}\`\n`);

report += `\n### Fragmented Tag Clusters (${findings.fragmentedClusters.length} found)\n`;
if (findings.fragmentedClusters.length === 0) report += `- None 🎉\n`;
else findings.fragmentedClusters.forEach(f => report += `- ${f}\n`);

report += `\n### Visibility Issues (${findings.visibilityIssues.length} found)\n`;
if (findings.visibilityIssues.length === 0) report += `- None 🎉\n`;
else findings.visibilityIssues.forEach(v => report += `- \`${v}\`\n`);

console.log("\nREPORT:\n");
console.log(report);

// Write to a temporary file
fs.writeFileSync(path.join(VAULT_ROOT, 'wiki_lint_report.tmp'), report);
