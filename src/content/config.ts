// @ts-check
import { defineCollection, z } from 'astro:content';

const parts = defineCollection({
  type: 'content',
  schema: z.object({
    title: z.string().optional(),
    part: z.string().optional(),
  }),
});

export const collections = { parts };
