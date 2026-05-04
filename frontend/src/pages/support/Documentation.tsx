import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Search, ArrowLeft, BookOpen, ArrowRight } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { SupportLayout } from "@/components/support/SupportLayout";
import { cn } from "@/lib/utils";

type Cat = "All" | "Learning" | "Technical" | "Others";

const allArticles = [
  { cat: "Learning", title: "How to access learning resources", desc: "Find your courses, modules, and downloadable materials." },
  { cat: "Learning", title: "How to submit assignments", desc: "Step-by-step guide to submitting your assignments on Aptem." },
  { cat: "Learning", title: "How to contact your tutor", desc: "Reach out to your assigned tutor for guidance." },
  { cat: "Technical", title: "How to reset password", desc: "Quickly reset your Aptem password if you've forgotten it." },
  { cat: "Technical", title: "How to fix login issues", desc: "Common login problems and their fixes." },
  { cat: "Technical", title: "How to upload files", desc: "Supported file types and upload limits." },
  { cat: "Others", title: "General support information", desc: "Overview of how Help Desk support works." },
  { cat: "Others", title: "Support response times", desc: "Our SLA targets for replying to your tickets." },
  { cat: "Others", title: "How to track your ticket", desc: "Check status updates and ticket history." },
];

const categories: Cat[] = ["All", "Learning", "Technical", "Others"];

const Documentation = () => {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [cat, setCat] = useState<Cat>("All");
  const [openArticle, setOpenArticle] = useState<typeof allArticles[number] | null>(null);

  const filtered = useMemo(
    () =>
      allArticles.filter(
        (a) =>
          (cat === "All" || a.cat === cat) &&
          (q === "" || a.title.toLowerCase().includes(q.toLowerCase()) || a.desc.toLowerCase().includes(q.toLowerCase()))
      ),
    [q, cat]
  );

  const related = openArticle ? allArticles.filter((a) => a.cat === openArticle.cat && a.title !== openArticle.title).slice(0, 3) : [];

  return (
    <SupportLayout>
      <div className="max-w-5xl mx-auto">
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="mb-4">
          <ArrowLeft className="h-4 w-4 mr-2" /> Back
        </Button>
        <div className="text-center mb-8">
          <div className="mx-auto h-12 w-12 rounded-2xl gradient-primary flex items-center justify-center shadow-card mb-3">
            <BookOpen className="h-6 w-6 text-primary-foreground" />
          </div>
          <h1 className="text-3xl font-bold mb-1">Help Documentation</h1>
          <p className="text-muted-foreground">Find answers and guides for everything Aptem.</p>
        </div>

        <div className="relative max-w-xl mx-auto mb-6">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search articles…"
            className="pl-10 h-12 rounded-xl"
          />
        </div>

        <div className="flex flex-wrap justify-center gap-2 mb-7">
          {categories.map((c) => (
            <button
              key={c}
              onClick={() => setCat(c)}
              className={cn(
                "px-4 py-1.5 rounded-full text-sm font-medium border transition-colors",
                cat === c
                  ? "gradient-primary border-transparent text-primary-foreground"
                  : "bg-card border-border hover:bg-secondary"
              )}
            >
              {c}
            </button>
          ))}
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((a) => (
            <article key={a.title} className="bg-card rounded-2xl border shadow-soft p-5 hover:shadow-card hover:-translate-y-0.5 transition-all flex flex-col">
              <span className="inline-flex self-start text-xs font-medium px-2.5 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 mb-3">
                {a.cat}
              </span>
              <h3 className="font-semibold mb-1.5">{a.title}</h3>
              <p className="text-sm text-muted-foreground flex-1">{a.desc}</p>
              <Button variant="outline" size="sm" className="mt-4 self-start" onClick={() => setOpenArticle(a)}>
                Read Article <ArrowRight className="h-3.5 w-3.5 ml-1.5" />
              </Button>
            </article>
          ))}
          {filtered.length === 0 && (
            <div className="col-span-full text-center text-muted-foreground py-12">
              No articles match your search.
            </div>
          )}
        </div>
      </div>

      <Dialog open={!!openArticle} onOpenChange={(o) => !o && setOpenArticle(null)}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <span className="inline-flex self-start text-xs font-medium px-2.5 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20 mb-1">
              {openArticle?.cat}
            </span>
            <DialogTitle className="text-2xl">{openArticle?.title}</DialogTitle>
          </DialogHeader>
          <div className="prose prose-sm max-w-none text-muted-foreground space-y-3">
            <p>{openArticle?.desc}</p>
            <p>
              This is a placeholder article body. Replace with real CMS content. It typically
              includes step-by-step instructions, screenshots, and links to related resources
              so learners can self-serve quickly.
            </p>
            <ol className="list-decimal pl-5 space-y-1 text-foreground">
              <li>Open your Aptem dashboard.</li>
              <li>Navigate to the relevant section.</li>
              <li>Follow the on-screen instructions.</li>
              <li>Contact support if you need further help.</li>
            </ol>
          </div>
          {related.length > 0 && (
            <div className="border-t pt-4">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mb-2">
                Related articles
              </div>
              <ul className="space-y-1.5">
                {related.map((r) => (
                  <li key={r.title}>
                    <button onClick={() => setOpenArticle(r)} className="text-sm text-primary hover:underline">
                      {r.title}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpenArticle(null)}>
              <ArrowLeft className="h-4 w-4 mr-2" /> Back to Documentation
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </SupportLayout>
  );
};

export default Documentation;
