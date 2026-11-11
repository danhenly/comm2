// @ts-check
// Content-sync pipeline: vault md -> src/content/parts, public/pdfs, src/data/exams
// Usage: node scripts/sync-content.mjs [--check]
//   --check = validate only, no writes
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');

const VAULT =
  process.env.VAULT_REVIEWERS ||
  '/mnt/c/Users/DNLPTP/Projects/DanOS/DanOS/School/4L/Comm2/Reviewers';

const CHECK = process.argv.includes('--check');

const PARTS = {
  'part-i-a': 'Part I-A General Concepts - Insurance Contract.md',
  'part-i-b': 'Part I-B Grounds for Rescission.md',
  'part-i-c': 'Part I-C Loss Settlement Subrogation.md',
  'part-i-d': 'Part I-D Classes of Insurance.md',
  'part-i-e': 'Part I-E Regulation of Insurance Business.md',
  'part-i-f': 'Part I-F Pre-Need Plans.md',
  'part-ii-a': 'Part II-A Contract of Common Carriage.md',
  'part-ii-b': 'Part II-B Obligations of the Parties.md',
  'part-ii-c': 'Part II-C Defenses of the Common Carrier.md',
  'part-ii-d': 'Part II-D Actions and Damages.md',
  'part-ii-e': 'Part II-E Air Transport and Montreal Convention.md',
  'part-ii-f': 'Part II-F Maritime Law.md',
  'part-iii-a': 'Part III-A Concept Agencies Constitutional Frame.md',
  'part-iii-b': 'Part III-B Authority to Operate CPC.md',
  'part-iii-c': 'Part III-C Due Process Rates Transfers Offenses.md',
  'part-iv-a': 'Part IV-A Competition Foundations Scope Market.md',
  'part-iv-b': 'Part IV-B Prohibited Conduct Mergers.md',
  'part-iv-c': 'Part IV-C PCC Confidentiality Remedies.md',
};

const PDFS = [
  'Part I (Compiled, Ch.1-6).pdf',
  'Part II (Compiled, Ch.7-13).pdf',
  'Part III (Compiled, Ch.14).pdf',
  'Part IV (Compiled, Ch.15).pdf',
];

const Q_RE = /^\*\*(?:(\d{4})\s+Bar\s+Q:\s*|Q:\s*)(.*)\*\*$/;
const BARE_CITE_RE = /\(\d{5,}\)/g;

function parseFile(slug, filename, raw) {
  const lines = raw.split(/\r?\n/);
  const items = [];
  let section = '';
  let i = 0;

  // bare-number cite warnings (don't fail)
  lines.forEach((line, idx) => {
    let m;
    BARE_CITE_RE.lastIndex = 0;
    while ((m = BARE_CITE_RE.exec(line)) !== null) {
      const prior = line.slice(Math.max(0, m.index - 20), m.index);
      if (!prior.includes('G.R. No.')) {
        console.warn(`WARN bare-number cite ${filename}:${idx + 1} ${m[0]} (no "G.R. No." in prior 20 chars)`);
      }
    }
  });

  while (i < lines.length) {
    const trimmed = lines[i].trim();
    if (trimmed.startsWith('## ')) {
      section = trimmed.slice(3).trim();
      i++;
      continue;
    }
    const qm = Q_RE.exec(trimmed);
    if (!qm) {
      i++;
      continue;
    }
    const year = qm[1] || undefined;
    const stem = (qm[2] || '').trim();
    const qLine = i + 1;

    // After each stem, skip blank lines AND lines starting with > (scope notes),
    // then require an A: line.
    let j = i + 1;
    while (j < lines.length) {
      const t = lines[j].trim();
      if (t === '' || t.startsWith('>')) j++;
      else break;
    }
    if (j >= lines.length || !lines[j].trim().startsWith('A:')) {
      throw new Error(`${filename}:${qLine} Q-without-A (stem: ${stem.slice(0, 80)})`);
    }
    // Collect the contiguous non-blank lines as the answer.
    const ansLines = [];
    let k = j;
    while (k < lines.length && lines[k].trim() !== '') {
      ansLines.push(lines[k]);
      k++;
    }
    let answer = ansLines.join('\n').trim().replace(/^A:\s*/, '');

    const n = items.length + 1;
    const item = {
      id: `${slug}-q${String(n).padStart(2, '0')}`,
      part: slug,
      section,
      stem,
      answer,
      kind: year ? 'historic' : 'drafted',
      ...(year ? { year } : {}),
      profile: 'P1',
      authorities: `${filename} :: ${section}`,
    };
    items.push(item);
    i = k;
  }
  return items;
}

function main() {
  const failures = [];
  const perPart = {};
  const allItems = [];
  const rawBySlug = {};

  for (const [slug, filename] of Object.entries(PARTS)) {
    const vaultPath = path.join(VAULT, filename);
    if (!fs.existsSync(vaultPath)) {
      failures.push(`${filename}: missing file at ${vaultPath}`);
      continue;
    }
    const raw = fs.readFileSync(vaultPath, 'utf8');
    rawBySlug[slug] = raw;
    try {
      const items = parseFile(slug, filename, raw);
      perPart[slug] = items;
      allItems.push(...items);
    } catch (err) {
      failures.push(err instanceof Error ? err.message : String(err));
    }
  }

  // PDF existence check (missing = failure, even in --check).
  for (const pdf of PDFS) {
    const p = path.join(VAULT, pdf);
    if (!fs.existsSync(p)) {
      failures.push(`${pdf}: missing file at ${p}`);
    }
  }

  let total = 0;
  for (const [slug, items] of Object.entries(perPart)) {
    console.log(`${slug}: ${items.length} items`);
    total += items.length;
  }
  console.log(`TOTAL: ${total} items`);

  if (failures.length > 0) {
    for (const f of failures) console.error(`FAIL: ${f}`);
    process.exit(1);
  }

  if (CHECK) {
    console.log('CHECK OK');
    return;
  }

  // Writes.
  const partsDir = path.join(ROOT, 'src/content/parts');
  const examsDir = path.join(ROOT, 'src/data/exams');
  const pdfsDir = path.join(ROOT, 'public/pdfs');
  fs.mkdirSync(partsDir, { recursive: true });
  fs.mkdirSync(examsDir, { recursive: true });
  fs.mkdirSync(pdfsDir, { recursive: true });

  for (const [slug, filename] of Object.entries(PARTS)) {
    const raw = rawBySlug[slug];
    const frontmatter = `---\ntitle: "${slug}"\npart: "${slug}"\n---\n\n`;
    fs.writeFileSync(path.join(partsDir, `${slug}.md`), frontmatter + raw);
    fs.writeFileSync(
      path.join(examsDir, `${slug}.json`),
      JSON.stringify(perPart[slug], null, 2) + '\n'
    );
  }
  fs.writeFileSync(path.join(examsDir, 'all.json'), JSON.stringify(allItems, null, 2) + '\n');

  for (const pdf of PDFS) {
    fs.copyFileSync(path.join(VAULT, pdf), path.join(pdfsDir, pdf));
  }

  console.log('SYNC OK');
}

main();
