export const SITE_TITLE = 'Pickleball Mania';
export const SITE_DESCRIPTION = 'Toute l\'actualité du pickleball en France et dans le monde. Tests, conseils, équipement et guide pour débuter.';
export const SITE_URL = 'https://pickleballmania.fr';

export const CATEGORIES = {
  actualites: {
    label: 'Actualités',
    description: 'Les dernières nouvelles du monde du pickleball en France et à l\'international.',
    color: 'bg-blue-100 text-blue-700',
    colorDot: 'bg-blue-500',
  },
  tests: {
    label: 'Tests & Avis',
    description: 'Nos tests détaillés de raquettes, balles et équipements de pickleball.',
    color: 'bg-purple-100 text-purple-700',
    colorDot: 'bg-purple-500',
  },
  conseils: {
    label: 'Conseils',
    description: 'Techniques, stratégies et astuces pour progresser au pickleball.',
    color: 'bg-teal-100 text-teal-700',
    colorDot: 'bg-teal-500',
  },
  equipement: {
    label: 'Équipement',
    description: 'Guides d\'achat et comparatifs d\'équipement de pickleball.',
    color: 'bg-amber-100 text-amber-700',
    colorDot: 'bg-amber-500',
  },
  debuter: {
    label: 'Débuter',
    description: 'Tout ce qu\'il faut savoir pour commencer le pickleball.',
    color: 'bg-green-100 text-green-700',
    colorDot: 'bg-green-500',
  },
} as const;

export type CategoryKey = keyof typeof CATEGORIES;
