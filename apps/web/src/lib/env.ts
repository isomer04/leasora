import { z } from 'zod';

const envSchema = z.object({
  NEXT_PUBLIC_API_BASE_URL: z.string().url().default('http://localhost:8000'),
});

type Env = z.infer<typeof envSchema>;

let env: Env | null = null;

export function getEnv(): Env {
  if (env) {
    return env;
  }

  try {
    env = envSchema.parse({
      NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
    });
  } catch (error) {
    if (error instanceof z.ZodError) {
      console.error('Invalid environment variables:', error.issues);
      throw new Error('Invalid environment variables');
    }
    throw error;
  }

  return env;
}

export const API_BASE_URL = getEnv().NEXT_PUBLIC_API_BASE_URL;
