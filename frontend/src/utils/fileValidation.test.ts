import { describe, expect, it } from "vitest";
import { validateMriFile } from "./fileValidation";

describe("validateMriFile", () => {
  it("accepts both NIfTI extensions within the configured client-side limit", () => {
    expect(validateMriFile(new File(["nifti"], "flair.nii"))).toBeNull();
    expect(validateMriFile(new File(["nifti"], "flair.nii.gz"))).toBeNull();
  });

  it("rejects empty, invalid, and oversized browser selections", () => {
    expect(validateMriFile(new File([], "flair.nii.gz"))).toBe(
      "The selected file is empty.",
    );
    expect(validateMriFile(new File(["not-nifti"], "flair.dcm"))).toBe(
      "Choose a NIfTI .nii or .nii.gz file.",
    );
    expect(
      validateMriFile(
        new File([new Uint8Array(64 * 1024 * 1024 + 1)], "flair.nii"),
      ),
    ).toBe("The selected file exceeds the 64 MB upload limit.");
  });
});
