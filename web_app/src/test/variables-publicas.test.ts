import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

// Vite incrusta toda variable VITE_* en el bundle público. Solo admito estas,
// que no son secretos. Agregar otra exige revisarla y sumarla aquí a propósito.
const VARIABLES_PUBLICAS_PERMITIDAS = new Set([
  "VITE_API_BASE",
]);

const PATRON_SENSIBLE = /(KEY|TOKEN|SECRET|SEED|MNEMONIC|PRIVATE|PASSWORD)/;

function archivosFuente(directorio: string): string[] {
  return readdirSync(directorio).flatMap((nombre) => {
    const ruta = join(directorio, nombre);
    if (statSync(ruta).isDirectory()) return archivosFuente(ruta);
    return /\.(ts|tsx)$/.test(nombre) && !/\.test\.tsx?$/.test(nombre) ? [ruta] : [];
  });
}

function variablesUsadas(): Map<string, string[]> {
  const raiz = join(process.cwd(), "src");
  const usadas = new Map<string, string[]>();
  for (const archivo of archivosFuente(raiz)) {
    const contenido = readFileSync(archivo, "utf-8");
    for (const coincidencia of contenido.matchAll(/import\.meta\.env\.(VITE_[A-Z0-9_]+)/g)) {
      const lista = usadas.get(coincidencia[1]) ?? [];
      lista.push(relative(raiz, archivo));
      usadas.set(coincidencia[1], lista);
    }
  }
  return usadas;
}

describe("variables VITE_* del frontend", () => {
  it("solo usa variables públicas aprobadas", () => {
    const noAprobadas = [...variablesUsadas().keys()].filter((nombre) => !VARIABLES_PUBLICAS_PERMITIDAS.has(nombre));
    expect(noAprobadas).toEqual([]);
  });

  it("no aprueba nombres que parezcan secretos", () => {
    const sospechosas = [...VARIABLES_PUBLICAS_PERMITIDAS].filter((nombre) => PATRON_SENSIBLE.test(nombre));
    expect(sospechosas).toEqual([]);
  });
});
