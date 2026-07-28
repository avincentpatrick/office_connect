import { api } from "./http";
import type { LoginResponse, MeResponse, MfaEnrollResponse, OkResponse } from "./types";

export function login(identifier: string, password: string): Promise<LoginResponse> {
  return api<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ identifier, password }),
  });
}

export function mfaVerify(mfaToken: string, code: string): Promise<LoginResponse> {
  return api<LoginResponse>("/auth/mfa/verify", {
    method: "POST",
    body: JSON.stringify({ mfa_token: mfaToken, code }),
  });
}

export function logout(): Promise<OkResponse> {
  return api<OkResponse>("/auth/logout", { method: "POST" });
}

export function fetchMe(): Promise<MeResponse> {
  return api<MeResponse>("/auth/me");
}

export function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<OkResponse> {
  return api<OkResponse>("/auth/password/change", {
    method: "POST",
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  });
}

export function mfaEnroll(): Promise<MfaEnrollResponse> {
  return api<MfaEnrollResponse>("/auth/mfa/enroll", { method: "POST" });
}

export function mfaConfirm(code: string): Promise<OkResponse> {
  return api<OkResponse>("/auth/mfa/confirm", {
    method: "POST",
    body: JSON.stringify({ code }),
  });
}
