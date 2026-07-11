import fs from "node:fs";
import path from "node:path";

export type E2EEnvironment = {
  name: string;
  webBaseUrl: string;
  identityBaseUrl: string;
  subscriptionBaseUrl: string;
  notificationBaseUrl: string;
  keycloakUrl: string;
  keycloakRealm: string;
  googleRedirectUri: string;
  readOnlySmoke?: boolean;
};

const ENV_DIR = path.join(__dirname, "..", "environments");

export function loadE2EEnvironment(name = process.env.E2E_ENV ?? "local"): E2EEnvironment {
  const file = path.join(ENV_DIR, `${name}.json`);
  if (!fs.existsSync(file)) {
    throw new Error(`Unknown E2E environment "${name}". Expected ${file}`);
  }
  return JSON.parse(fs.readFileSync(file, "utf8")) as E2EEnvironment;
}

export function googleIdTokenFromEnv(): string | undefined {
  const token = process.env.GOOGLE_ID_TOKEN?.trim();
  return token || undefined;
}
