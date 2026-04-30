import { Navigate, useLocation } from "react-router-dom";
import { SparkLoading } from "../design";
import { canAccessProtectedRoute } from "./guard";
import { useAuth } from "./AuthProvider";

interface RouteGuardProps {
  children: React.ReactNode;
}

export default function RouteGuard({ children }: RouteGuardProps) {
  const location = useLocation();
  const { mode, status } = useAuth();

  if (status === "loading") {
    return <SparkLoading description="Checking session…" />;
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
