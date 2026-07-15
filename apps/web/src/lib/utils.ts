import { twMerge } from 'tailwind-merge';

export function cn(...inputs: Array<string | undefined | null | false | 0>): string {
  const filtered = inputs.filter((input): input is string => typeof input === 'string' && input.length > 0);
  return twMerge(filtered);
}
