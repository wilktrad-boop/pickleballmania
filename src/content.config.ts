import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { z } from 'astro/zod';

const blog = defineCollection({
	loader: glob({ base: './src/content/blog', pattern: '**/*.{md,mdx}' }),
	schema: ({ image }) =>
		z.object({
			title: z.string(),
			description: z.string(),
			pubDate: z.coerce.date(),
			updatedDate: z.coerce.date().optional(),
			heroImage: z.optional(image()),
			category: z.enum(['actualites', 'tests', 'conseils', 'equipement', 'debuter']).default('actualites'),
			tags: z.array(z.string()).default([]),
			author: z.string().default('Pickleball Mania'),
			affiliateProducts: z.array(z.object({
				name: z.string(),
				url: z.string(),
				price: z.string(),
				image: z.string().optional(),
			})).optional(),
		}),
});

export const collections = { blog };
