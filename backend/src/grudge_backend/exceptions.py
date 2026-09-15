"""Small helpers for translating domain-layer failures into HTTP responses.
Routers catch service-layer exceptions (FolderCycleError, etc.) explicitly and
call these rather than relying on global exception-handler middleware - more
explicit for a surface this small.
"""

from __future__ import annotations

from fastapi import HTTPException, status


def not_found(detail: str = "Not found.") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


def bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def unauthorized(detail: str = "Authentication required.") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def forbidden(detail: str) -> HTTPException:
    """Unlike folders/automata (strictly private per-user resources, where the
    convention is always-404-never-403 to avoid leaking existence), sim rooms
    are inherently shared/multi-user by design (invite-code based) - a room's
    existence isn't secret, so "you can't do this specific action" is
    correctly a 403 here, not a 404.
    """
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
