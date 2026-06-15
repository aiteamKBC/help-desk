import { useDeferredValue, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { LoaderCircle, Search } from "lucide-react";
import { SupportLayout } from "@/components/support/SupportLayout";
import { AttachmentPanel } from "@/components/knowledge-base/AttachmentPanel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  archiveKnowledgeBaseArticle,
  buildArticleSearchText,
  buildEvidencePayload,
  buildKnowledgeBaseArticleUrl,
  chooseArticleFilename,
  createAttachmentId,
  createEmptyArticle,
  createStaticHtml,
  fetchKnowledgeBaseArticles,
  formatKnowledgeBaseDate,
  KNOWLEDGE_BASE_APP_VERSION,
  KNOWLEDGE_BASE_DRAFT_STORAGE_KEY,
  KNOWLEDGE_BASE_SECTIONS,
  normalizeArticleData,
  prepareArticleForSave,
  readDataUrl,
  resolveAttachmentUrl,
  safeFileName,
  saveKnowledgeBaseArticle,
  stripEmbeddedAttachmentData,
  type KnowledgeBaseArticleData,
  type KnowledgeBaseArticleIndexItem,
  type KnowledgeBaseSectionKey,
} from "@/lib/knowledgeBase";
import { cn } from "@/lib/utils";

type WorkspaceView = "builder" | "center";
type StatusTone = "neutral" | "success" | "error";

type DraftIdentity = {
  id?: string;
  fileName?: string;
  path?: string;
};

const workspaceCardClassName = "rounded-[28px] border border-slate-200/90 bg-white shadow-card";

function statusClassName(tone: StatusTone) {
  if (tone === "success") {
    return "border-emerald-200 bg-emerald-50/90 text-emerald-700";
  }
  if (tone === "error") {
    return "border-rose-200 bg-rose-50 text-rose-700";
  }
  return "border-emerald-100 bg-emerald-50/80 text-emerald-700";
}

function articleFromIndexItem(item: KnowledgeBaseArticleIndexItem): KnowledgeBaseArticleData {
  if (item.json) {
    return normalizeArticleData(JSON.parse(item.json));
  }

  return {
    ...createEmptyArticle(),
    title: item.title,
    keywords: item.keywords,
    createdAt: item.createdAt,
    updatedAt: item.updatedAt,
    exportedAt: item.exportedAt || "",
    sections: {
      inquiry: item.sections?.inquiry || "",
      summary: item.sections?.summary || "",
      steps: item.sections?.steps || "",
      resources: item.sections?.resources || "",
    },
    attachments: {
      inquiry: item.attachments?.inquiry || [],
      summary: item.attachments?.summary || [],
      steps: item.attachments?.steps || [],
      resources: item.attachments?.resources || [],
    },
  };
}

const KnowledgeBaseWorkspace = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [view, setView] = useState<WorkspaceView>("center");
  const [draft, setDraft] = useState<KnowledgeBaseArticleData>(createEmptyArticle);
  const [draftIdentity, setDraftIdentity] = useState<DraftIdentity | null>(null);
  const [articles, setArticles] = useState<KnowledgeBaseArticleIndexItem[]>([]);
  const [searchInput, setSearchInput] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [statusMessage, setStatusMessage] = useState("Ready.");
  const [statusTone, setStatusTone] = useState<StatusTone>("neutral");
  const [isLoadingArticles, setIsLoadingArticles] = useState(true);
  const [isSavingArticle, setIsSavingArticle] = useState(false);
  const [isRemovingArticle, setIsRemovingArticle] = useState<string | null>(null);
  const [areBuilderToolsVisible, setAreBuilderToolsVisible] = useState(true);
  const deferredSearchQuery = useDeferredValue(searchQuery);

  const setStatus = (message: string, tone: StatusTone = "neutral") => {
    setStatusMessage(message);
    setStatusTone(tone);
  };

  const loadArticles = async ({ silent = false }: { silent?: boolean } = {}) => {
    try {
      setIsLoadingArticles(true);
      const nextArticles = await fetchKnowledgeBaseArticles();
      setArticles(nextArticles);
      if (!silent) {
        setStatus(`Indexed ${nextArticles.length} article${nextArticles.length === 1 ? "" : "s"}.`, "success");
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not load the article index.";
      setStatus(message, "error");
    } finally {
      setIsLoadingArticles(false);
    }
  };

  useEffect(() => {
    void loadArticles({ silent: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- Run the initial article bootstrap once on mount.
  }, []);

  useEffect(() => {
    const savedDraft = window.localStorage.getItem(KNOWLEDGE_BASE_DRAFT_STORAGE_KEY);
    if (!savedDraft) {
      return;
    }

    try {
      setDraft(normalizeArticleData(JSON.parse(savedDraft)));
    } catch {
      window.localStorage.removeItem(KNOWLEDGE_BASE_DRAFT_STORAGE_KEY);
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem(KNOWLEDGE_BASE_DRAFT_STORAGE_KEY, JSON.stringify(draft));
  }, [draft]);

  useEffect(() => {
    const nextEditArticle = (location.state as { editArticle?: KnowledgeBaseArticleIndexItem } | null)?.editArticle;
    if (!nextEditArticle) {
      return;
    }

    setDraft(normalizeArticleData(articleFromIndexItem(nextEditArticle)));
    setDraftIdentity({
      id: nextEditArticle.id,
      fileName: nextEditArticle.fileName,
      path: nextEditArticle.path,
    });
    setView("builder");
    setAreBuilderToolsVisible(true);
    setStatus(`Opened ${nextEditArticle.title} for editing.`, "success");
    navigate("/knowledge-base", { replace: true });
  }, [location.state, navigate]);

  const queryWords = deferredSearchQuery
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean);

  const filteredArticles = (queryWords.length
    ? articles.filter((article) => {
        const haystack = buildArticleSearchText(article);
        return queryWords.every((word) => haystack.includes(word));
      })
    : articles.slice()).sort((left, right) => left.title.localeCompare(right.title));

  const updateSectionText = (section: KnowledgeBaseSectionKey, value: string) => {
    setDraft((currentDraft) => ({
      ...currentDraft,
      sections: {
        ...currentDraft.sections,
        [section]: value,
      },
    }));
  };

  const updateAttachments = (
    section: KnowledgeBaseSectionKey,
    updater: (
      currentAttachments: KnowledgeBaseArticleData["attachments"][KnowledgeBaseSectionKey],
    ) => KnowledgeBaseArticleData["attachments"][KnowledgeBaseSectionKey],
  ) => {
    setDraft((currentDraft) => ({
      ...currentDraft,
      attachments: {
        ...currentDraft.attachments,
        [section]: updater(currentDraft.attachments[section] || []),
      },
    }));
  };

  const openAttachment = (sectionAttachment: { url?: string; evidencePath?: string; dataUrl?: string }) => {
    const source = resolveAttachmentUrl({
      id: "preview",
      name: "Attachment",
      type: "",
      ...sectionAttachment,
    });
    if (!source) {
      return;
    }
    window.open(source, "_blank", "noopener,noreferrer");
  };

  const addFilesToSection = async (section: KnowledgeBaseSectionKey, files: File[]) => {
    try {
      const attachments = await Promise.all(
        files.map(async (file) => {
          const name = safeFileName(file.name, "attachment");
          return {
            id: createAttachmentId(),
            name,
            type: file.type || "application/octet-stream",
            size: file.size,
            evidencePath: `Evidence/${name}`,
            dataUrl: await readDataUrl(file),
          };
        }),
      );
      updateAttachments(section, (currentAttachments) => [...currentAttachments, ...attachments]);
      setStatus(`Added ${attachments.length} attachment${attachments.length === 1 ? "" : "s"} to ${section}.`, "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not add the attachment files.";
      setStatus(message, "error");
    }
  };

  const addLinkToSection = (section: KnowledgeBaseSectionKey) => {
    const url = window.prompt("Paste the attachment or source link:");
    if (!url) {
      return;
    }

    const trimmedUrl = url.trim();
    if (!trimmedUrl) {
      return;
    }

    updateAttachments(section, (currentAttachments) => [
      ...currentAttachments,
      {
        id: createAttachmentId(),
        name: trimmedUrl,
        type: "link",
        url: trimmedUrl,
      },
    ]);
    setStatus(`Added a link to ${section}.`, "success");
  };

  const clearDraft = (message = "Draft cleared. Ready for a new article.") => {
    setDraft(createEmptyArticle());
    setDraftIdentity(null);
    setView("builder");
    setAreBuilderToolsVisible(true);
    setStatus(message, "success");
  };

  const startNewArticle = () => {
    clearDraft("New article draft ready.");
  };

  const editIndexedArticle = (item: KnowledgeBaseArticleIndexItem) => {
    setDraft(articleFromIndexItem(item));
    setDraftIdentity({
      id: item.id,
      fileName: item.fileName,
      path: item.path,
    });
    setView("builder");
    setAreBuilderToolsVisible(true);
    setStatus(`Opened ${item.title} for editing.`, "success");
  };

  const saveDraft = async () => {
    try {
      setIsSavingArticle(true);
      const timestamp = new Date().toISOString();
      const preparedDraft = prepareArticleForSave({
        ...draft,
        createdAt: draft.createdAt || timestamp,
        updatedAt: draft.createdAt ? timestamp : "",
      });
      const articleToStore = stripEmbeddedAttachmentData(preparedDraft);
      const fileName = chooseArticleFilename(articleToStore, articles, draftIdentity?.fileName);
      const html = createStaticHtml(articleToStore);
      const result = await saveKnowledgeBaseArticle({
        filename: fileName,
        html,
        evidence: buildEvidencePayload(preparedDraft),
      });

      const savedDraft = articleFromIndexItem(result.article);
      setDraft(savedDraft);
      setDraftIdentity({
        id: result.article.id,
        fileName,
        path: result.path,
      });
      await loadArticles({ silent: true });
      setStatus(`Saved article to Articles/${fileName} and synced its evidence files.`, "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not save the article.";
      setStatus(message, "error");
    } finally {
      setIsSavingArticle(false);
    }
  };

  const archiveArticle = async (item: KnowledgeBaseArticleIndexItem) => {
    const confirmed = window.confirm(`Archive "${item.title}" and move it into Articles/Bin?`);
    if (!confirmed) {
      return;
    }

    try {
      setIsRemovingArticle(item.fileName);
      const result = await archiveKnowledgeBaseArticle(item.fileName);
      await loadArticles({ silent: true });
      if (draftIdentity?.fileName === item.fileName) {
        setDraft(createEmptyArticle());
        setDraftIdentity(null);
      }
      setStatus(`Archived ${item.title} to ${result.path}.`, "success");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not archive the article.";
      setStatus(message, "error");
    } finally {
      setIsRemovingArticle(null);
    }
  };

  const applySearch = () => {
    setSearchQuery(searchInput);
  };

  const clearSearch = () => {
    setSearchInput("");
    setSearchQuery("");
  };

  return (
    <SupportLayout fullWidth mainClassName="px-0 py-0 sm:px-0 md:px-0 xl:px-0">
      <div className="fixed inset-x-0 top-[74px] z-20 flex w-full flex-col gap-4 border-y border-slate-200/80 bg-white/92 px-4 py-4 shadow-[0_18px_34px_-28px_rgba(15,23,42,0.38)] backdrop-blur-md sm:top-[84px] sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-[max(2rem,calc((100vw-1120px)/2+2rem))] lg:py-5">
        <div className="min-w-0">
          <h1 className="text-[2.1rem] font-semibold tracking-tight text-slate-950">Knowledge Base</h1>
          <p className="mt-2 max-w-2xl text-[15px] leading-6 text-slate-500">Search, open, and edit technical support articles.</p>
        </div>

        <div className="inline-flex w-fit self-start rounded-full border border-slate-200 bg-slate-100/95 p-1.5 shadow-[inset_0_1px_0_rgba(255,255,255,0.92)] lg:self-auto">
          <button
            type="button"
            onClick={() => setView("center")}
            className={cn(
              "rounded-full px-5 py-2.5 text-sm font-semibold transition-all",
              view === "center"
                ? "bg-primary text-primary-foreground shadow-[0_10px_22px_-14px_rgba(79,70,229,0.78)]"
                : "text-slate-700 hover:bg-white hover:text-slate-900",
            )}
          >
            Knowledge Base
          </button>
          <button
            type="button"
            onClick={() => {
              setView("builder");
              setAreBuilderToolsVisible(true);
            }}
            className={cn(
              "rounded-full px-5 py-2.5 text-sm font-semibold transition-all",
              view === "builder"
                ? "bg-primary text-primary-foreground shadow-[0_10px_22px_-14px_rgba(79,70,229,0.78)]"
                : "text-slate-700 hover:bg-white hover:text-slate-900",
            )}
          >
            Article Creation
          </button>
        </div>
      </div>

      <div aria-hidden="true" className="mb-[70px] h-[182px] sm:h-[174px] lg:h-[152px]" />

      <div className="relative overflow-x-hidden">
        <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
          <div className="absolute left-1/2 top-6 h-[320px] w-[860px] -translate-x-1/2 rounded-full bg-[radial-gradient(circle_at_center,rgba(111,91,204,0.12),rgba(255,255,255,0))]" />
          <div className="absolute bottom-0 left-1/2 h-[420px] w-[980px] -translate-x-1/2 rounded-full bg-[radial-gradient(circle_at_center,rgba(148,163,184,0.10),rgba(255,255,255,0))]" />
        </div>

        <div className="relative mx-auto w-full max-w-[1120px] px-4 pb-14 pt-0 sm:px-6 lg:px-8">
          <div>
            {view === "center" ? (
              <Card className={cn(workspaceCardClassName, "overflow-hidden")}>
                <CardHeader className="space-y-5 pb-5">
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div>
                      <CardTitle className="text-[2rem] font-semibold tracking-tight text-slate-950">Knowledge Center</CardTitle>
                      <CardDescription className="mt-3 max-w-3xl text-base leading-7 text-slate-500">
                        Open existing articles and search by title, keywords, inquiry, summary, steps, or resources.
                      </CardDescription>
                    </div>
                    <Badge
                      variant="secondary"
                      className="rounded-full border border-primary/10 bg-primary/10 px-3 py-1 text-sm font-semibold text-primary"
                    >
                      {articles.length} article{articles.length === 1 ? "" : "s"} indexed
                    </Badge>
                  </div>

                  <form
                    className="space-y-3"
                    onSubmit={(event) => {
                      event.preventDefault();
                      applySearch();
                    }}
                  >
                    <label htmlFor="kb-search" className="block text-base font-semibold text-slate-950">
                      Search articles
                    </label>
                    <div className="flex flex-col gap-3 md:flex-row md:items-center">
                      <div className="relative flex-1">
                        <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                        <Input
                          id="kb-search"
                          value={searchInput}
                          onChange={(event) => setSearchInput(event.target.value)}
                          placeholder="Search by keyword or title, for example MFA, Teams, Aptem"
                          className="h-12 rounded-2xl border-slate-200 bg-white pl-11 text-sm shadow-none"
                        />
                      </div>
                      <div className="flex gap-2">
                        <Button type="submit" className="h-11 rounded-2xl px-5 font-semibold">
                          Search
                        </Button>
                        <Button type="button" variant="secondary" className="h-11 rounded-2xl px-5 font-semibold" onClick={clearSearch}>
                          Clear
                        </Button>
                      </div>
                    </div>
                  </form>
                </CardHeader>

                <CardContent className="space-y-4">
                  {isLoadingArticles ? (
                    <div className="flex min-h-[220px] items-center justify-center rounded-[24px] border border-dashed border-slate-200 bg-slate-50 text-slate-500">
                      <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
                      Loading articles...
                    </div>
                  ) : null}

                  {!isLoadingArticles && !filteredArticles.length ? (
                    <div className="rounded-[24px] border border-dashed border-slate-200 bg-slate-50 px-5 py-12 text-center text-slate-500">
                      No matching articles found.
                    </div>
                  ) : null}

                  {!isLoadingArticles ? (
                    <div className="grid gap-4">
                      {filteredArticles.map((item) => {
                        const createdAt = formatKnowledgeBaseDate(item.createdAt || item.exportedAt);
                        const updatedAt = formatKnowledgeBaseDate(item.updatedAt);
                        const isRemoving = isRemovingArticle === item.fileName;

                        return (
                          <article
                            key={item.id}
                            className="rounded-[24px] border border-slate-200/90 bg-white px-4 py-4 shadow-soft sm:px-5"
                          >
                            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                              <div className="min-w-0 flex-1">
                                <h3 className="text-[1.85rem] font-semibold tracking-tight text-slate-950">
                                  {item.title || "Untitled article"}
                                </h3>
                                <p className="mt-2 text-sm leading-6 text-slate-500">
                                  <span className="font-semibold text-slate-900">Keywords:</span>{" "}
                                  {item.keywords || "No keywords"}
                                </p>
                                <div className="mt-2 text-xs leading-6 text-slate-500">
                                  {item.fileName}
                                  {createdAt ? ` | Created: ${createdAt}` : ""}
                                  {updatedAt ? ` | Edited: ${updatedAt}` : ""}
                                </div>
                              </div>

                              <div className="flex flex-wrap gap-2 lg:justify-end">
                                <Button
                                  type="button"
                                  className="h-9 rounded-xl px-4 font-semibold"
                                  onClick={() => navigate(buildKnowledgeBaseArticleUrl(item.fileName), { state: { article: item } })}
                                >
                                  Open
                                </Button>
                                <Button
                                  type="button"
                                  variant="secondary"
                                  className="h-9 rounded-xl border border-slate-200 bg-slate-100 px-4 font-semibold text-slate-800 hover:bg-slate-200"
                                  onClick={() => editIndexedArticle(item)}
                                >
                                  Edit
                                </Button>
                                <Button
                                  type="button"
                                  variant="ghost"
                                  className="h-9 rounded-xl bg-rose-50 px-4 font-semibold text-rose-600 hover:bg-rose-100 hover:text-rose-700"
                                  onClick={() => archiveArticle(item)}
                                  disabled={isRemoving}
                                >
                                  {isRemoving ? <LoaderCircle className="h-4 w-4 animate-spin" /> : "Remove"}
                                </Button>
                              </div>
                            </div>
                          </article>
                        );
                      })}
                    </div>
                  ) : null}
                </CardContent>
              </Card>
            ) : (
              <div className="grid gap-6 xl:grid-cols-[250px_minmax(0,1fr)]">
                {areBuilderToolsVisible ? (
                  <aside className="xl:sticky xl:top-[172px] xl:self-start">
                    <Card className={cn(workspaceCardClassName, "overflow-hidden")}>
                      <CardHeader className="pb-4">
                        <div className="flex items-center justify-between gap-3">
                          <CardTitle className="text-lg font-semibold text-slate-950">Article tools</CardTitle>
                          <Button
                            type="button"
                            variant="secondary"
                            size="sm"
                            className="h-8 rounded-full px-3 text-xs font-semibold"
                            onClick={() => setAreBuilderToolsVisible(false)}
                          >
                            Hide
                          </Button>
                        </div>
                      </CardHeader>

                      <CardContent className="space-y-4">
                        <div className="grid gap-2">
                          <Button type="button" className="h-11 rounded-2xl font-semibold" onClick={startNewArticle}>
                            New article
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            className="h-11 rounded-2xl bg-rose-50 font-semibold text-rose-600 hover:bg-rose-100 hover:text-rose-700"
                            onClick={() => clearDraft()}
                          >
                             Clear form
                          </Button>
                        </div>

                        <div className={cn("rounded-2xl border px-4 py-3 text-sm", statusClassName(statusTone))}>
                          <div className="font-semibold">{statusMessage}</div>
                          <div className="mt-1 text-xs opacity-80">Version: {KNOWLEDGE_BASE_APP_VERSION}</div>
                        </div>
                      </CardContent>
                    </Card>
                  </aside>
                ) : null}

                <section className="space-y-5">
                  {!areBuilderToolsVisible ? (
                    <div className="flex justify-start">
                      <Button
                        type="button"
                        variant="secondary"
                        className="h-10 rounded-full border border-slate-200 bg-white px-4 font-semibold text-slate-700 hover:bg-slate-50"
                        onClick={() => setAreBuilderToolsVisible(true)}
                      >
                        Show article tools
                      </Button>
                    </div>
                  ) : null}

                  <Card className={cn(workspaceCardClassName, "overflow-hidden")}>
                    <CardHeader className="pb-5">
                      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                        <div>
                          <CardTitle className="text-[1.9rem] font-semibold tracking-tight text-slate-950">Article Creation</CardTitle>
                        </div>
                        <Button type="button" className="h-11 rounded-2xl px-5 font-semibold" onClick={saveDraft} disabled={isSavingArticle}>
                          {isSavingArticle ? <LoaderCircle className="h-4 w-4 animate-spin" /> : "Save article"}
                        </Button>
                      </div>
                    </CardHeader>

                    <CardContent className="grid gap-4 md:grid-cols-2">
                      <div className="space-y-2">
                        <label className="text-sm font-semibold text-slate-950" htmlFor="kb-title">
                          Article title
                        </label>
                        <Input
                          id="kb-title"
                          value={draft.title}
                          onChange={(event) => setDraft((currentDraft) => ({ ...currentDraft, title: event.target.value }))}
                          placeholder="Example: Reset Microsoft Authenticator"
                          className="h-12 rounded-2xl border-slate-200 bg-white shadow-none"
                        />
                      </div>

                      <div className="space-y-2">
                        <label className="text-sm font-semibold text-slate-950" htmlFor="kb-keywords">
                          Keywords
                        </label>
                        <Input
                          id="kb-keywords"
                          value={draft.keywords}
                          onChange={(event) => setDraft((currentDraft) => ({ ...currentDraft, keywords: event.target.value }))}
                          placeholder="authenticator, MFA, reset, phone"
                          className="h-12 rounded-2xl border-slate-200 bg-white shadow-none"
                        />
                      </div>
                    </CardContent>
                  </Card>

                  {KNOWLEDGE_BASE_SECTIONS.map((section) => (
                    <Card key={section.key} className={cn(workspaceCardClassName, "shadow-soft")}>
                      <CardHeader className="pb-4">
                        <div className="flex items-start justify-between gap-4">
                          <div>
                            <CardTitle className="text-[1.75rem] font-semibold tracking-tight text-slate-950">
                              {section.heading}
                            </CardTitle>
                          </div>
                          <Badge
                            variant="secondary"
                            className="rounded-full border border-primary/10 bg-primary/10 px-3 py-1 text-xs font-semibold text-primary"
                          >
                            {section.badge}
                          </Badge>
                        </div>
                      </CardHeader>

                      <CardContent>
                        <label className="mb-2 block text-sm font-semibold text-slate-950" htmlFor={`kb-${section.key}`}>
                          {section.label}
                        </label>
                        <Textarea
                          id={`kb-${section.key}`}
                          value={draft.sections[section.key]}
                          onChange={(event) => updateSectionText(section.key, event.target.value)}
                          placeholder={section.placeholder}
                          className={cn(
                            "min-h-[150px] resize-y rounded-2xl border-slate-200 bg-white text-sm leading-6 shadow-none",
                            section.key !== "inquiry" && "font-mono text-[13px]",
                          )}
                        />
                        <AttachmentPanel
                          attachments={draft.attachments[section.key]}
                          onAddFiles={(files) => addFilesToSection(section.key, files)}
                          onAddLink={() => addLinkToSection(section.key)}
                          onOpenAttachment={(attachment) => openAttachment(attachment)}
                          onRemoveAttachment={(attachmentId) =>
                            updateAttachments(section.key, (currentAttachments) =>
                              currentAttachments.filter((attachment) => attachment.id !== attachmentId),
                            )
                          }
                        />
                      </CardContent>
                    </Card>
                  ))}
                </section>
              </div>
            )}

            <div className="pt-10 text-center text-xs text-slate-500">Internal knowledge base.</div>
          </div>
        </div>
      </div>
    </SupportLayout>
  );
};

export default KnowledgeBaseWorkspace;
