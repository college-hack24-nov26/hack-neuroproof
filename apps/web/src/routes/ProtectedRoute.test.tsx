import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProtectedRoute } from "./ProtectedRoute";

const { useAuthMock } = vi.hoisted(() => ({ useAuthMock: vi.fn() }));

vi.mock("../hooks/useAuth", () => ({
  useAuth: () => useAuthMock(),
}));

function renderProtectedRoute() {
  return render(
    <MemoryRouter initialEntries={["/app"]}>
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route element={<p>Authorized workspace</p>} path="/app" />
        </Route>
        <Route element={<p>Sign in</p>} path="/hospital-login" />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProtectedRoute", () => {
  beforeEach(() => {
    useAuthMock.mockReset();
  });

  it("redirects an unauthenticated browser to the hospital sign-in route", () => {
    useAuthMock.mockReturnValue({ actor: null, isInitializing: false });
    renderProtectedRoute();
    expect(screen.getByText("Sign in")).toBeInTheDocument();
  });

  it("renders protected content for an active hospital actor", () => {
    useAuthMock.mockReturnValue({
      actor: { role: "doctor" },
      isInitializing: false,
    });
    renderProtectedRoute();
    expect(screen.getByText("Authorized workspace")).toBeInTheDocument();
  });
});
