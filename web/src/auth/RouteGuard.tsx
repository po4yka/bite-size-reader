import { Navigate, useLocation } from "react-router-dom";
import { InlineLoading } from "@carbon/react";
import { canAccessProtectedRoute } from "./guard";
import { useAuth } from "./AuthProvider";

interface RouteGuardProps {
  children: JSX.Element;
}

export default function RouteGuard({ children }: RouteGuardProps) {
  const location = useLocation();
  const { mode, status } = useAuth();

  if (status === "loading") {
    return <InlineLoading description="Checking session…" />;
  }

  if (!canAccessProtectedRoute(mode, status)) {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: `${location.pathname}${location.search}${location.hash}` }}
      />
    );
  }

  return children;
}
