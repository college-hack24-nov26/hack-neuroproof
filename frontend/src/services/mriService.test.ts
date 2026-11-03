import { afterEach, describe, expect, it, vi } from "vitest";
import { mriService } from "./mriService";

describe("mriService.modelInfo", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("preflights the selected Global FedAvg checkpoint through the API", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          model_source: "global_fedavg_abc",
          model_name: "MONAI 3D U-Net",
          modality_order: ["flair", "t1", "t1ce", "t2"],
          architecture: {},
          expected_parameter_count: 2453636,
          configured: true,
          integrity_status: "verified",
          checkpoint: {
            sha256: "a".repeat(64),
            size_bytes: 1,
          },
          model_loaded: false,
        }),
        { headers: { "Content-Type": "application/json" }, status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const response = await mriService.modelInfo("global_fedavg_abc");

    expect(response.integrity_status).toBe("verified");
    const [url, options] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/model/info?model_source=global_fedavg_abc");
    expect(new Headers(options.headers).get("Accept")).toBe("application/json");
  });
});
