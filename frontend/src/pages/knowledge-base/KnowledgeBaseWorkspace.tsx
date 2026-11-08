import { useDeferredValue, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { AlertCircle, ArrowLeft, CheckCircle2, Eraser, FilePlus2, LoaderCircle, Plus, Save, Search } from "lucide-react";
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

const workspaceCardClassName = "rounded-2xl border bg-card shadow-[0_1px_3px_rgba(23,21,43,0.05)]";

function statusClassName(tone: StatusTone) {
  if (tone === "success") {
    return "border-[#C9E8D2] bg-[#E8F6EC] text-[#237A45]";
  }
  if (tone === "error") {
    return "border-rose-200 bg-rose-50 text-rose-700";
  }
  return "border-[#C9E8D2] bg-[#E8F6EC]/70 text-[#237A45]";
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

  const tabClassName = (active: boolean) =>
    cn(
      "rounded-full px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
      active ? "bg-primary text-primary-foreground shadow-[0_6px_16px_-10px_rgba(91,33,232,0.7)]" : "text-muted-foreground hover:bg-secondary hover:text-primary",
    );
  const fieldLabelClassName = "block text-[13px] font-medium text-foreground";
  const fieldControlClassName = "rounded-xl border-input bg-card text-sm text-foreground shadow-none placeholder:text-muted-foreground/80";

  return (
    <SupportLayout fullWidth mainClassName="px-0 py-0 sm:px-0 md:px-0 xl:px-0">
      <div className="mx-auto w-full max-w-[1160px] px-4 pb-14 pt-8 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="min-w-0">
            <h1 className="text-[28px] font-semibold leading-9 tracking-tight text-foreground">Knowledge Base</h1>
            <p className="mt-1 text-sm text-muted-foreground">Search, open, and edit technical support articles.</p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate("/admin")}
            className="h-10 rounded-full border-primary/30 bg-white px-4 hover:bg-primary/5 hover:text-primary"
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Button>
          <div className="inline-flex w-fit shrink-0 gap-1 rounded-full border bg-card p-1 shadow-[0_1px_2px_rgba(23,21,43,0.04)]">
            <button
              type="button"
              aria-pressed={view === "center"}
              onClick={() => setView("center")}
              className={tabClassName(view === "center")}
            >
              Knowledge Base
            </button>
            <button
              type="button"
              aria-pressed={view === "builder"}
              onClick={() => {
                setView("builder");
                setAreBuilderToolsVisible(true);
              }}
              className={tabClassName(view === "builder")}
            >
              Article Creation
            </button>
          </div>
          </div>
        </div>

        <div className="mt-6">
          {view === "center" ? (
            <Card className={workspaceCardClassName}>
              <CardHeader className="space-y-5 p-5 pb-4 sm:p-6 sm:pb-5">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <CardTitle className="text-xl font-semibold tracking-tight text-foreground">Knowledge Center</CardTitle>
                    <CardDescription className="mt-1 text-sm leading-6 text-muted-foreground">
                      Open existing articles and search by title, keywords, inquiry, summary, steps, or resources.
                    </CardDescription>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Badge
                      variant="secondary"
                      className="h-8 rounded-full border bg-secondary px-3 text-xs font-medium text-primary hover:bg-secondary"
                    >
                      {articles.length} article{articles.length === 1 ? "" : "s"} indexed
                    </Badge>
                    <Button type="button" className="h-8 gap-1.5 rounded-lg px-3 text-sm font-medium" onClick={startNewArticle}>
                      <Plus className="h-4 w-4" aria-hidden />
                      New
                    </Button>
                  </div>
                </div>

                <form
                  className="space-y-2"
                  onSubmit={(event) => {
                    event.preventDefault();
                    applySearch();
                  }}
                >
                  <label htmlFor="kb-search" className={fieldLabelClassName}>
                    Search articles
                  </label>
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                    <div className="relative flex-1">
                      <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                      <Input
                        id="kb-search"
                        value={searchInput}
                        onChange={(event) => setSearchInput(event.target.value)}
                        placeholder="Search by keyword or title, for example MFA, Teams, Aptem"
                        className={cn(fieldControlClassName, "h-11 pl-10")}
                      />
                    </div>
                    <div className="flex gap-2">
                      <Button type="submit" className="h-11 flex-1 rounded-xl px-5 text-sm font-medium sm:flex-none">
                        Search
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        className="h-11 flex-1 rounded-xl border-input bg-card px-5 text-sm font-medium text-foreground hover:bg-secondary hover:text-primary sm:flex-none"
                        onClick={clearSearch}
                      >
                        Clear
                      </Button>
                    </div>
                  </div>
                </form>
              </CardHeader>

              <CardContent className="space-y-3 p-5 pt-0 sm:p-6 sm:pt-0">
                {isLoadingArticles ? (
                  <div className="flex min-h-[200px] items-center justify-center rounded-xl border border-dashed bg-secondary/60 text-sm text-muted-foreground">
                    <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
                    Loading articles...
                  </div>
                ) : null}

                {!isLoadingArticles && !filteredArticles.length ? (
                  <div className="rounded-xl border border-dashed bg-secondary/60 px-5 py-10 text-center text-sm text-muted-foreground">
                    No matching articles found.
                  </div>
                ) : null}

                {!isLoadingArticles ? (
                  <div className="grid gap-3">
                    {filteredArticles.map((item) => {
                      const createdAt = formatKnowledgeBaseDate(item.createdAt || item.exportedAt);
                      const updatedAt = formatKnowledgeBaseDate(item.updatedAt);
                      const isRemoving = isRemovingArticle === item.fileName;

                      return (
                        <article
                          key={item.id}
                          className="rounded-xl border bg-card px-4 py-4 transition-colors hover:border-primary/25 hover:bg-secondary sm:px-5"
                        >
                          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between md:gap-6">
                            <div className="min-w-0 flex-1">
                              <h3 className="text-base font-medium leading-6 text-foreground">
                                {item.title || "Untitled article"}
                              </h3>
                              <p className="mt-1.5 text-sm leading-6 text-muted-foreground">
                                <span className="font-medium text-foreground">Keywords:</span>{" "}
                                {item.keywords || "No keywords"}
                              </p>
                              <div className="mt-1.5 flex flex-col gap-0.5 text-xs leading-5 text-muted-foreground sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-2">
                                <span className="break-all">{item.fileName}</span>
                                {createdAt ? <><span aria-hidden className="hidden text-border sm:inline">|</span><span>Created: {createdAt}</span></> : null}
                                {updatedAt ? <><span aria-hidden className="hidden text-border sm:inline">|</span><span>Edited: {updatedAt}</span></> : null}
                              </div>
                            </div>

                            <div className="flex shrink-0 flex-wrap gap-2">
                              <Button
                                type="button"
                                className="h-8 rounded-lg px-4 text-[13px] font-medium"
                                onClick={() => navigate(buildKnowledgeBaseArticleUrl(item.fileName), { state: { article: item } })}
                              >
                                Open
                              </Button>
                              <Button
                                type="button"
                                variant="outline"
                                className="h-8 rounded-lg border-input bg-card px-4 text-[13px] font-medium text-foreground hover:bg-secondary hover:text-primary"
                                onClick={() => editIndexedArticle(item)}
                              >
                                Edit
                              </Button>
                              <Button
                                type="button"
                                variant="outline"
                                className="h-8 min-w-[76px] rounded-lg border-rose-200 bg-card px-4 text-[13px] font-medium text-rose-600 hover:border-rose-300 hover:bg-rose-50 hover:text-rose-700"
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
            <div className={cn("grid gap-5", areBuilderToolsVisible && "lg:grid-cols-[248px_minmax(0,1fr)]")}>
              {areBuilderToolsVisible ? (
                <aside className="lg:sticky lg:top-6 lg:self-start">
                  <Card className={workspaceCardClassName}>
                    <CardHeader className="p-4 pb-3">
                      <div className="flex items-center justify-between gap-3">
                        <CardTitle className="text-sm font-semibold text-foreground">Article tools</CardTitle>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-7 rounded-full border-input bg-secondary px-3 text-xs font-medium text-primary hover:border-primary/30 hover:bg-secondary hover:text-primary"
                          onClick={() => setAreBuilderToolsVisible(false)}
                        >
                          Hide
                        </Button>
                      </div>
                    </CardHeader>

                    <CardContent className="space-y-3 p-4 pt-0">
                      <div className="grid gap-2">
                        <Button type="button" className="h-9 gap-2 rounded-lg text-[13px] font-medium" onClick={startNewArticle}>
                          <FilePlus2 className="h-4 w-4" aria-hidden />
                          New article
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          className="h-9 gap-2 rounded-lg border-input bg-secondary text-[13px] font-medium text-primary hover:border-primary/30 hover:bg-secondary hover:text-primary"
                          onClick={() => clearDraft()}
                        >
                          <Eraser className="h-4 w-4" aria-hidden />
                          Clear form
                        </Button>
                      </div>

                      <div role="status" className={cn("rounded-lg border px-3 py-2.5", statusClassName(statusTone))}>
                        <div className="flex items-start gap-1.5 text-[13px] font-medium">
                          {statusTone === "error"
                            ? <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                            : <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />}
                          <span>{statusMessage}</span>
                        </div>
                        <div className="mt-1 break-words text-xs opacity-80">Version: {KNOWLEDGE_BASE_APP_VERSION}</div>
                      </div>
                    </CardContent>
                  </Card>
                </aside>
              ) : null}

              <section className="min-w-0 space-y-4">
                {!areBuilderToolsVisible ? (
                  <Button
                    type="button"
                    variant="outline"
                    className="h-8 rounded-full border-input bg-card px-4 text-[13px] font-medium text-primary hover:bg-secondary hover:text-primary"
                    onClick={() => setAreBuilderToolsVisible(true)}
                  >
                    Show article tools
                  </Button>
                ) : null}

                <Card className={workspaceCardClassName}>
                  <CardHeader className="p-5 pb-4 sm:p-6 sm:pb-4">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                      <div className="min-w-0">
                        <CardTitle className="text-xl font-semibold tracking-tight text-foreground">Article Creation</CardTitle>
                        <CardDescription className="mt-1 text-xs text-muted-foreground">
                          Fill in the title, keywords and each section to build a new support article.
                        </CardDescription>
                      </div>
                      <Button
                        type="button"
                        className="h-9 min-w-[124px] shrink-0 gap-2 rounded-lg px-4 text-[13px] font-medium"
                        onClick={saveDraft}
                        disabled={isSavingArticle}
                      >
                        {isSavingArticle ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <><Save className="h-4 w-4" aria-hidden />Save article</>}
                      </Button>
                    </div>
                  </CardHeader>

                  <CardContent className="grid gap-4 p-5 pt-0 sm:p-6 sm:pt-0 md:grid-cols-2">
                    <div className="space-y-1.5">
                      <label className={fieldLabelClassName} htmlFor="kb-title">
                        Article title
                      </label>
                      <Input
                        id="kb-title"
                        value={draft.title}
                        onChange={(event) => setDraft((currentDraft) => ({ ...currentDraft, title: event.target.value }))}
                        placeholder="Example: Reset Microsoft Authenticator"
                        className={cn(fieldControlClassName, "h-11")}
                      />
                    </div>

                    <div className="space-y-1.5">
                      <label className={fieldLabelClassName} htmlFor="kb-keywords">
                        Keywords
                      </label>
                      <Input
                        id="kb-keywords"
                        value={draft.keywords}
                        onChange={(event) => setDraft((currentDraft) => ({ ...currentDraft, keywords: event.target.value }))}
                        placeholder="authenticator, MFA, reset, phone"
                        className={cn(fieldControlClassName, "h-11")}
                      />
                    </div>
                  </CardContent>
                </Card>

                {KNOWLEDGE_BASE_SECTIONS.map((section) => (
                  <Card key={section.key} className={workspaceCardClassName}>
                    <CardHeader className="p-5 pb-3 sm:p-6 sm:pb-3">
                      <div className="flex items-center justify-between gap-4">
                        <CardTitle className="text-lg font-semibold tracking-tight text-foreground">
                          {section.heading}
                        </CardTitle>
                        <Badge
                          variant="secondary"
                          className="shrink-0 rounded-full border bg-secondary px-2.5 py-0.5 text-xs font-medium text-primary hover:bg-secondary"
                        >
                          {section.badge}
                        </Badge>
                      </div>
                    </CardHeader>

                    <CardContent className="p-5 pt-0 sm:p-6 sm:pt-0">
                      <label className={cn(fieldLabelClassName, "mb-1.5")} htmlFor={`kb-${section.key}`}>
                        {section.label}
                      </label>
                      <Textarea
                        id={`kb-${section.key}`}
                        value={draft.sections[section.key]}
                        onChange={(event) => updateSectionText(section.key, event.target.value)}
                        placeholder={section.placeholder}
                        className={cn(fieldControlClassName, "min-h-[140px] resize-y leading-6")}
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

          <div className="pt-10 text-center text-xs text-muted-foreground">Internal knowledge base.</div>
        </div>
      </div>
    </SupportLayout>
  );
};

export default KnowledgeBaseWorkspace;
