import { useEffect, useState } from "react";
import { useNavigate, Link, useLocation } from "react-router-dom";
import { ArrowLeft, ArrowRight, Eye, EyeOff, Lock, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SupportCampusHero } from "@/components/support/SupportCampusHero";
import { SupportLayout } from "@/components/support/SupportLayout";
import {
  adminPortalReturnQueryParam,
  getOrCreateAdminBrowserInstanceId,
  setAdminSession,
} from "@/lib/adminSession";
import "./EmailVerification.css";
import "./AdminLogin.css";
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

const MicrosoftTeamsIcon = () => (
  <svg
    className="microsoft-teams-icon"
    viewBox="0 0 24 24"
    aria-hidden="true"
    focusable="false"
  >
    <circle cx="17.2" cy="5.1" r="2.15" fill="#7B83EB" />
    <circle cx="20.7" cy="7.1" r="1.55" fill="#5059C9" />
    <path d="M16.2 8.1h2.7c1.1 0 2 .9 2 2v4.1a3.35 3.35 0 0 1-6.7 0v-4.1c0-1.1.9-2 2-2Z" fill="#5059C9" />
    <path d="M10.1 6.4h4.6c1.2 0 2.2 1 2.2 2.2v6.1a4.5 4.5 0 0 1-9 0V8.6c0-1.2 1-2.2 2.2-2.2Z" fill="#7B83EB" />
    <rect x="2.2" y="7.2" width="10.2" height="10.2" rx="1.65" fill="#4B53BC" />
    <path d="M4.45 9.55h5.7v1.45H8.02v4.3H6.56V11H4.45V9.55Z" fill="#FFFFFF" />
  </svg>
);

const AdminLogin = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [browserInstanceId] = useState(() => getOrCreateAdminBrowserInstanceId());
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
    ? `${microsoftPortalOrigin}/api/admin/microsoft/login?origin=${encodeURIComponent(microsoftPortalOrigin)}&instanceId=${encodeURIComponent(browserInstanceId)}`
    : `/api/admin/microsoft/login?instanceId=${encodeURIComponent(browserInstanceId)}`;

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
      const instanceId = browserInstanceId;
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
    <SupportLayout landing showHeader={false} mainClassName="support-landing-main admin-login-main">
      {/* Same destination as the Support Portal link the admin header rendered before. */}
      <Link
        to={{ pathname: "/", search: `?${adminPortalReturnQueryParam}=1` }}
        className="admin-login-portal"
      >
        <ArrowLeft aria-hidden="true" />
        <span>Support Portal</span>
      </Link>

      <SupportCampusHero
        title={<>Admin access,<br />made simple.</>}
        subtitle="Secure sign in for the support team."
      />

      <section className="support-entry admin-login-entry" aria-labelledby="admin-login-title">
        <div className="admin-login-content">
          <div className="admin-login-heading">
            <h1 id="admin-login-title">Admin Login</h1>
            <p>Sign in to access the admin dashboard.</p>
          </div>

          <form onSubmit={(event) => void handleSubmit(event)} className="admin-login-form">
            <div className="admin-login-field">
              <label htmlFor="username" className="sr-only">Username</label>
              <UserRound aria-hidden="true" />
              <Input
                id="username"
                value={username}
                onChange={(event) => {
                  setUsername(event.target.value);
                  setError("");
                }}
                placeholder="admin"
                autoComplete="username"
              />
            </div>
            <div className="admin-login-field admin-login-field--password">
              <label htmlFor="password" className="sr-only">Password</label>
              <Lock aria-hidden="true" />
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
              />
              <button
                type="button"
                onClick={() => setShowPass((currentValue) => !currentValue)}
                className="admin-login-toggle"
                aria-label={showPass ? "Hide password" : "Show password"}
              >
                {showPass ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
              </button>
            </div>

            {error && (
              <div className="admin-login-error" role="alert">
                {error}
              </div>
            )}

            <Button type="submit" className="admin-login-submit" disabled={isSubmitting}>
              {isSubmitting ? "Signing In..." : "Sign In"}
              {!isSubmitting && <ArrowRight aria-hidden="true" />}
            </Button>

            <div className="admin-login-divider">
              <span>or continue with</span>
            </div>

            <Button asChild variant="outline" className="admin-login-teams">
              <a href={microsoftLoginUrl}>
                <MicrosoftTeamsIcon />
                Sign in with Microsoft Teams
              </a>
            </Button>

            <div className="admin-login-notes">
              <p>Use an active support username and the password configured on the server.</p>
              <p>Use your Kent Microsoft work account for direct admin access.</p>
              <p>
                Need support access?{" "}
                <Link to="/support">Go to Support</Link>
              </p>
            </div>
          </form>
        </div>
      </section>
    </SupportLayout>
  );
};

export default AdminLogin;
