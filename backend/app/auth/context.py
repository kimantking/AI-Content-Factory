from __future__ import annotations

from dataclasses import dataclass, field

# highest privilege first
ROLE_RANK = {"OWNER": 5, "ADMIN": 4, "PUBLISHER": 3, "EDITOR": 2, "ANALYST": 1, "VIEWER": 0}

# capability → minimum role
CAPABILITY_MIN_ROLE = {
    "workspace.manage": "OWNER",
    "member.manage": "OWNER",
    "budget.write": "ADMIN",
    "brand.write": "ADMIN",
    "channel.write": "ADMIN",
    "autopilot.write": "ADMIN",
    "sponsor.write": "ADMIN",
    "affiliate.write": "ADMIN",
    "content.write": "EDITOR",
    "campaign.create": "EDITOR",
    "publish.approve": "PUBLISHER",
    "publish.run": "PUBLISHER",
    "analytics.read": "ANALYST",
    "revenue.read": "ANALYST",
    "read": "VIEWER",
}


def role_at_least(role: str | None, minimum: str) -> bool:
    return ROLE_RANK.get(role or "", -1) >= ROLE_RANK.get(minimum, 99)


@dataclass
class AuthContext:
    user_id: str
    email: str = ""
    is_system_admin: bool = False
    workspace_id: str | None = None
    role: str | None = None                     # role in the active workspace
    memberships: dict[str, str] = field(default_factory=dict)  # workspace_id -> role

    # ---- checks -------------------------------------------------------- #

    def can(self, capability: str) -> bool:
        if self.is_system_admin:
            return True
        minimum = CAPABILITY_MIN_ROLE.get(capability, "OWNER")
        return role_at_least(self.role, minimum)

    def require(self, capability: str) -> None:
        from fastapi import HTTPException

        if not self.can(capability):
            raise HTTPException(403, f"role '{self.role or 'none'}' lacks capability '{capability}'")

    def role_in(self, workspace_id: str) -> str | None:
        if self.is_system_admin:
            return "OWNER"
        return self.memberships.get(workspace_id)

    def assert_workspace(self, workspace_id: str | None) -> None:
        """IDOR guard — raise unless this user is a member of `workspace_id`
        (system admins pass). Used by every workspace-scoped resource."""
        from fastapi import HTTPException

        if workspace_id is None:
            raise HTTPException(400, "resource has no workspace scope")
        if self.is_system_admin:
            return
        if workspace_id not in self.memberships:
            raise HTTPException(403, "resource belongs to another workspace")
