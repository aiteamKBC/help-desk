import { useEffect, useState } from "react";
import { useNavigate, Link, useLocation } from "react-router-dom";
import { Lock, ShieldCheck, Eye, EyeOff, Building2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SupportLayout } from "@/components/support/SupportLayout";
import { createAdminSessionInstanceId, setAdminSession } from "@/lib/adminSession";
import { buildCsrfHeaders } from "@/lib/csrf";
import { toast } from "sonner";

interface LoginResponse {
  message?: string;
  admin?: {
    id: number;
    username: string;
    fullName: string;
    email: string | null;
    role: string;
    instanceId?: string;
    consoleStatus?: string;
  };
}

const AdminLogin = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const microsoftPortalOrigin = typeof window !== "undefined"
    ? (() => {
        const { protocol, hostname, port, origin } = window.location;
        if (hostname === "127.0.0.1") {
          return `${protocol}//localhost${port ? `:${port}` : ""}`;
        }
        return origin;
      })()
    : "";
  const microsoftLoginUrl = microsoftPortalOrigin
    ? `${microsoftPortalOrigin}/api/admin/microsoft/login?origin=${encodeURIComponent(microsoftPortalOrigin)}`
    : "/api/admin/microsoft/login";

  useEffect(() => {
    const controller = new AbortController();

    void fetch("/api/admin/session", {
      method: "GET",
      signal: controller.signal,
    }).catch(() => undefined);

    return () => controller.abort();
  }, []);

  useEffect(() => {
    const searchParams = new URLSearchParams(location.search);
    const microsoftError = searchParams.get("microsoftError");
    if (microsoftError) {
      setError(microsoftError);
    }
  }, [location.search]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();

    if (!username.trim() || !password) {
      setError("Username and password are required.");
      return;
    }

    setIsSubmitting(true);

    try {
      const instanceId = createAdminSessionInstanceId();
      const response = await fetch("/api/admin/login", {
        method: "POST",
        headers: buildCsrfHeaders({
          "Content-Type": "application/json",
        }),
        body: JSON.stringify({
          username,
          password,
          instanceId,
          consoleStatus: "Off",
        }),
      });

      const payload = (await response.json().catch(() => null)) as LoginResponse | null;

      if (!response.ok || !payload?.admin) {
        setError(payload?.message || "Invalid username or password.");
        return;
      }

      setAdminSession({
        ...payload.admin,
        instanceId: payload.admin.instanceId || instanceId,
        consoleStatus: "Off",
      });
      toast.success(`Welcome back, ${payload.admin.fullName}`);
      navigate("/admin");
    } catch {
      setError("We could not connect to the server. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <SupportLayout>
      <div className="max-w-md mx-auto">
        <div className="bg-card rounded-2xl border shadow-card p-8">
          <div className="text-center mb-6">
            <div className="mx-auto h-12 w-12 rounded-2xl gradient-primary flex items-center justify-center shadow-card mb-3">
              <ShieldCheck className="h-6 w-6 text-primary-foreground" />
            </div>
            <h1 className="text-2xl font-bold">Admin Login</h1>
            <p className="text-muted-foreground text-sm mt-1">
              Sign in to access the admin dashboard.
            </p>
          </div>

          <form onSubmit={(event) => void handleSubmit(event)} className="space-y-4">
            <div>
              <Label htmlFor="username" className="mb-1.5 block">Username</Label>
              <Input
                id="username"
                value={username}
                onChange={(event) => {
                  setUsername(event.target.value);
                  setError("");
                }}
                placeholder="admin"
                autoComplete="username"
                className="h-11"
              />
            </div>
            <div>
              <Label htmlFor="password" className="mb-1.5 block">Password</Label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  id="password"
                  type={showPass ? "text" : "password"}
                  value={password}
                  onChange={(event) => {
                    setPassword(event.target.value);
                    setError("");
                  }}
                  placeholder="Enter your password"
                  autoComplete="current-password"
                  className="h-11 pl-9 pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPass((currentValue) => !currentValue)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  aria-label={showPass ? "Hide password" : "Show password"}
                >
                  {showPass ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {error && (
              <div className="text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg px-3 py-2">
                {error}
              </div>
            )}

            <Button type="submit" className="w-full gradient-primary border-0 h-11" disabled={isSubmitting}>
              {isSubmitting ? "Signing In..." : "Sign In"}
            </Button>

            <div className="relative py-1">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-border/70" />
              </div>
              <div className="relative flex justify-center text-[11px] uppercase tracking-[0.28em] text-muted-foreground">
                <span className="bg-card px-3">or continue with</span>
              </div>
            </div>

            <Button asChild variant="outline" className="w-full h-11 border-primary/20 text-foreground hover:bg-primary/5">
              <a href={microsoftLoginUrl}>
                <Building2 className="h-4 w-4 text-primary" />
                Sign in with Microsoft Teams
              </a>
            </Button>

            <div className="text-xs text-center text-muted-foreground pt-2">
              Use an active support username and the password configured on the server.
            </div>
            <div className="text-xs text-center text-muted-foreground">
              Use your Kent Microsoft work account for direct admin access.
            </div>
          </form>
        </div>

        <p className="text-center text-xs text-muted-foreground mt-4">
          Need support access?{" "}
          <Link to="/support" className="text-primary hover:underline">Go to Support</Link>
        </p>
      </div>
    </SupportLayout>
  );
};

export default AdminLogin;
