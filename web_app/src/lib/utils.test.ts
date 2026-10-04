import { describe, expect, it } from "vitest";
import { cn } from "./utils";

describe("cn", () => {
  it("resuelve conflictos de Tailwind dejando la última clase", () => {
    expect(cn("px-2 text-sm", "px-4")).toBe("text-sm px-4");
  });

  it("descarta valores falsos y respeta clases condicionales", () => {
    const activo = false;
    expect(cn("base", activo && "activo", undefined, null, { visible: true, oculto: false })).toBe("base visible");
  });
});
