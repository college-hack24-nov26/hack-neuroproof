import type { MriModality } from "../services/mriService";

const MAX_FILE_SIZE = 64 * 1024 * 1024;

export const MRI_MODALITIES: {
  id: MriModality;
  label: string;
  description: string;
}[] = [
  {
    id: "flair",
    label: "FLAIR",
    description: "Fluid-attenuated inversion recovery",
  },
  { id: "t1", label: "T1", description: "T1-weighted" },
  { id: "t1ce", label: "T1CE", description: "T1 contrast-enhanced" },
  { id: "t2", label: "T2", description: "T2-weighted" },
];

export function validateMriFile(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!name.endsWith(".nii") && !name.endsWith(".nii.gz")) {
    return "Choose a NIfTI .nii or .nii.gz file.";
  }
  if (file.size === 0) {
    return "The selected file is empty.";
  }
  if (file.size > MAX_FILE_SIZE) {
    return "The selected file exceeds the 64 MB upload limit.";
  }
  return null;
}
