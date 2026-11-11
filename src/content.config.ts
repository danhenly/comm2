// @ts-check
import { defineCollection, z } from 'astro:content';
import { glob } from 'astro/loaders';

const parts = defineCollection({
  loader: glob({ pattern: '**/*.md', base: './src/content/parts' }),
  schema: z.object({
    title: z.string().optional(),
    part: z.string().optional(),
  }),
});

export const collections = { parts };
