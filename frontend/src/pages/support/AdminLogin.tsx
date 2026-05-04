import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { Lock, ShieldCheck, ArrowLeft, Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SupportLayout } from "@/components/support/SupportLayout";
import { setAdminSession } from "@/lib/adminSession";
import { toast } from "sonner";

interface LoginResponse {
  message?: string;
  admin?: {
    id: number;
    username: string;
    fullName: string;
    email: string | null;
    role: string;
  };
}

const AdminLogin = () => {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();

    if (!username.trim() || !password) {
      setError("Username and password are required.");
      return;
    }

    setIsSubmitting(true);

    try {
      const response = await fetch("/api/admin/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          username,
          password,
        }),
      });

      const payload = (await response.json().catch(() => null)) as LoginResponse | null;

      if (!response.ok || !payload?.admin) {
        setError(payload?.message || "Invalid username or password.");
        return;
      }

      setAdminSession(payload.admin);
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
        <Button variant="ghost" size="sm" onClick={() => navigate("/")} className="mb-4">
          <ArrowLeft className="h-4 w-4 mr-2" /> Back
        </Button>
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

            <div className="text-xs text-center text-muted-foreground pt-2">
              Use an active support username. The local default password is <span className="font-mono">admin123</span>.
            </div>
          </form>
        </div>

        <p className="text-center text-xs text-muted-foreground mt-4">
          Need a learner account?{" "}
          <Link to="/support" className="text-primary hover:underline">Go to Support</Link>
        </p>
      </div>
    </SupportLayout>
  );
};

export default AdminLogin;
