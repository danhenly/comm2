export const PART_ORDER = [
  'part-i-a',
  'part-i-b',
  'part-i-c',
  'part-i-d',
  'part-i-e',
  'part-i-f',
  'part-ii-a',
  'part-ii-b',
  'part-ii-c',
  'part-ii-d',
  'part-ii-e',
  'part-ii-f',
  'part-iii-a',
  'part-iii-b',
  'part-iii-c',
  'part-iv-a',
  'part-iv-b',
  'part-iv-c',
] as const;

export type PartSlug = (typeof PART_ORDER)[number];

export const PART_LABEL: Record<PartSlug, string> = {
  'part-i-a': 'I-A General Concepts',
  'part-i-b': 'I-B Rescission',
  'part-i-c': 'I-C Loss/Settlement/Subrogation',
  'part-i-d': 'I-D Classes',
  'part-i-e': 'I-E Regulation',
  'part-i-f': 'I-F Pre-Need',
  'part-ii-a': 'II-A Carriage',
  'part-ii-b': 'II-B Obligations',
  'part-ii-c': 'II-C Defenses',
  'part-ii-d': 'II-D Damages',
  'part-ii-e': 'II-E Air/Montreal',
  'part-ii-f': 'II-F Maritime',
  'part-iii-a': 'III-A Concept/Agencies/Frame',
  'part-iii-b': 'III-B Authority/CPC',
  'part-iii-c': 'III-C Due Process/Rates/Offenses',
  'part-iv-a': 'IV-A Foundations/Scope/Market',
  'part-iv-b': 'IV-B Prohibited Conduct/Mergers',
  'part-iv-c': 'IV-C PCC/Confidentiality/Remedies',
};

export const PART_PDF: Record<string, string> = {
  'part-i-a': 'Part I (Compiled, Ch.1-6).pdf',
  'part-i-b': 'Part I (Compiled, Ch.1-6).pdf',
  'part-i-c': 'Part I (Compiled, Ch.1-6).pdf',
  'part-i-d': 'Part I (Compiled, Ch.1-6).pdf',
  'part-i-e': 'Part I (Compiled, Ch.1-6).pdf',
  'part-i-f': 'Part I (Compiled, Ch.1-6).pdf',
  'part-ii-a': 'Part II (Compiled, Ch.7-13).pdf',
  'part-ii-b': 'Part II (Compiled, Ch.7-13).pdf',
  'part-ii-c': 'Part II (Compiled, Ch.7-13).pdf',
  'part-ii-d': 'Part II (Compiled, Ch.7-13).pdf',
  'part-ii-e': 'Part II (Compiled, Ch.7-13).pdf',
  'part-ii-f': 'Part II (Compiled, Ch.7-13).pdf',
  'part-iii-a': 'Part III (Compiled, Ch.14).pdf',
  'part-iii-b': 'Part III (Compiled, Ch.14).pdf',
  'part-iii-c': 'Part III (Compiled, Ch.14).pdf',
  'part-iv-a': 'Part IV (Compiled, Ch.15).pdf',
  'part-iv-b': 'Part IV (Compiled, Ch.15).pdf',
  'part-iv-c': 'Part IV (Compiled, Ch.15).pdf',
};

export function pdfUrl(pdf: string) {
  return `/pdfs/${encodeURIComponent(pdf)}`;
}

export const GROUPS: { title: string; pdf: string; slugs: PartSlug[] }[] = [
  {
    title: 'Part I (Ch.1-6)',
    pdf: 'Part I (Compiled, Ch.1-6).pdf',
    slugs: ['part-i-a', 'part-i-b', 'part-i-c', 'part-i-d', 'part-i-e', 'part-i-f'],
  },
  {
    title: 'Part II (Ch.7-13)',
    pdf: 'Part II (Compiled, Ch.7-13).pdf',
    slugs: ['part-ii-a', 'part-ii-b', 'part-ii-c', 'part-ii-d', 'part-ii-e', 'part-ii-f'],
  },
  {
    title: 'Part III (Ch.14)',
    pdf: 'Part III (Compiled, Ch.14).pdf',
    slugs: ['part-iii-a', 'part-iii-b', 'part-iii-c'],
  },
  {
    title: 'Part IV (Ch.15)',
    pdf: 'Part IV (Compiled, Ch.15).pdf',
    slugs: ['part-iv-a', 'part-iv-b', 'part-iv-c'],
  },
];
