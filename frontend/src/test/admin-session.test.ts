import { describe, expect, it } from "vitest";
import { isSameAdminIdentity, isSameAdminSession, type AdminSession } from "@/lib/adminSession";

const baseSession: AdminSession = {
  id: 23,
  username: "Omar1",
  fullName: "Omar One",
  email: null,
  role: "admin",
  instanceId: "instance-one",
};

describe("admin session helpers", () => {
  it("treats same admin with a different instance as the same identity", () => {
    const nextSession: AdminSession = {
      ...baseSession,
      instanceId: "instance-two",
      username: "omar1",
    };

    expect(isSameAdminIdentity(baseSession, nextSession)).toBe(true);
    expect(isSameAdminSession(baseSession, nextSession)).toBe(false);
  });

  it("treats a different admin as a different identity", () => {
    const nextSession: AdminSession = {
      ...baseSession,
      id: 99,
      username: "ahmed",
      fullName: "Ahmed",
    };

    expect(isSameAdminIdentity(baseSession, nextSession)).toBe(false);
    expect(isSameAdminSession(baseSession, nextSession)).toBe(false);
  });
});
