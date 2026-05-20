import { useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ExternalLink, FilePenLine, FileText, ImageIcon, Link2, LoaderCircle } from "lucide-react";
import { SupportLayout } from "@/components/support/SupportLayout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  fetchKnowledgeBaseArticle,
  formatBytes,
  formatKnowledgeBaseDate,
  KNOWLEDGE_BASE_SECTIONS,
  linkifyText,
  normalizeArticleData,
  resolveAttachmentUrl,
  type KnowledgeBaseArticleData,
  type KnowledgeBaseArticleIndexItem,
} from "@/lib/knowledgeBase";

function articleDataFromItem(item: KnowledgeBaseArticleIndexItem): KnowledgeBaseArticleData {
  if (item.json) {
    return normalizeArticleData(JSON.parse(item.json));
  }

  return normalizeArticleData({
    title: item.title,
    keywords: item.keywords,
    createdAt: item.createdAt,
    updatedAt: item.updatedAt,
    exportedAt: item.exportedAt,
    sections: item.sections,
    attachments: item.attachments,
  });
}

function isImageAttachment(source: string, type: string) {
  return type.startsWith("image/") || /\.(png|jpe?g|gif|webp|svg)$/i.test(source) || source.startsWith("data:image/");
}

function isPdfAttachment(source: string, type: string) {
  return type === "application/pdf" || /\.pdf(?:$|\?)/i.test(source);
}

const KnowledgeBaseArticle = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const params = useParams<{ fileName: string }>();
  const routeFileName = params.fileName ? decodeURIComponent(params.fileName) : "";
  const locationState = location.state as { article?: KnowledgeBaseArticleIndexItem } | null;
  const [articleItem, setArticleItem] = useState<KnowledgeBaseArticleIndexItem | null>(
    locationState?.article?.fileName === routeFileName ? locationState.article : null,
  );
  const [isLoading, setIsLoading] = useState(!articleItem);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    if (!routeFileName) {
      setErrorMessage("No article file was provided.");
      setIsLoading(false);
      return;
    }

    if (locationState?.article?.fileName === routeFileName) {
      setArticleItem(locationState.article);
      setIsLoading(false);
      return;
    }

    let isActive = true;
    setIsLoading(true);
    setErrorMessage("");

    void (async () => {
      try {
        const nextArticle = await fetchKnowledgeBaseArticle(routeFileName);
        if (!isActive) {
          return;
        }
        setArticleItem(nextArticle);
      } catch (error) {
        if (!isActive) {
          return;
        }
        const message = error instanceof Error ? error.message : "Could not load the article.";
        setErrorMessage(message);
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    })();

    return () => {
      isActive = false;
    };
  }, [locationState?.article, routeFileName]);

  const articleData = articleItem ? articleDataFromItem(articleItem) : null;
  const createdAt = formatKnowledgeBaseDate(articleData?.createdAt || articleData?.exportedAt);
  const updatedAt = formatKnowledgeBaseDate(articleData?.updatedAt);

  if (isLoading) {
    return (
      <SupportLayout fullWidth>
        <div className="mx-auto flex min-h-[50vh] max-w-6xl items-center justify-center rounded-3xl border border-dashed border-border bg-slate-50 text-muted-foreground">
          <LoaderCircle className="mr-2 h-4 w-4 animate-spin" />
          Loading article...
        </div>
      </SupportLayout>
    );
  }

  if (!articleItem || !articleData) {
    return (
      <SupportLayout fullWidth>
        <div className="mx-auto max-w-5xl">
          <Card className="border-rose-200 bg-rose-50/80 shadow-soft">
            <CardContent className="space-y-4 p-6">
              <div className="text-lg font-semibold text-rose-700">Article unavailable</div>
              <p className="text-sm text-rose-700/90">{errorMessage || "The requested article could not be loaded."}</p>
              <Button type="button" variant="outline" onClick={() => navigate("/knowledge-base")}>
                <ArrowLeft className="h-4 w-4" />
                Back to Knowledge Base
              </Button>
            </CardContent>
          </Card>
        </div>
      </SupportLayout>
    );
  }

  return (
    <SupportLayout fullWidth>
      <div className="mx-auto max-w-6xl space-y-6">
        <Card className="overflow-hidden border-primary/10 shadow-card">
          <CardHeader className="bg-[linear-gradient(135deg,rgba(88,79,242,0.10),rgba(171,189,255,0.05))]">
            <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <Badge className="bg-white/90 text-primary" variant="secondary">
                  Knowledge Base Article
                </Badge>
                <CardTitle className="mt-4 text-3xl tracking-tight md:text-4xl">{articleData.title || "Untitled article"}</CardTitle>
                <div className="mt-4 flex flex-wrap gap-3 text-sm text-muted-foreground">
                  {createdAt ? (
                    <span className="rounded-full border border-border/80 bg-white/80 px-3 py-1">Created: {createdAt}</span>
                  ) : null}
                  {updatedAt ? (
                    <span className="rounded-full border border-border/80 bg-white/80 px-3 py-1">Edited: {updatedAt}</span>
                  ) : null}
                </div>
                <p className="mt-4 max-w-4xl text-sm leading-6 text-muted-foreground md:text-base">
                  <span className="font-semibold text-foreground">Keywords:</span> {articleData.keywords || "No keywords"}
                </p>
              </div>

              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="outline" onClick={() => navigate("/knowledge-base")}>
                  <ArrowLeft className="h-4 w-4" />
                  Back
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => navigate("/knowledge-base", { state: { editArticle: articleItem } })}
                >
                  <FilePenLine className="h-4 w-4" />
                  Edit in Builder
                </Button>
              </div>
            </div>
          </CardHeader>
        </Card>

        {KNOWLEDGE_BASE_SECTIONS.map((section) => {
          const attachments = articleData.attachments[section.key] || [];

          return (
            <Card key={section.key} className="border-border/80 shadow-soft">
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <CardTitle className="text-xl">{section.heading}</CardTitle>
                  <Badge variant="secondary" className="bg-primary/8 text-primary">
                    {section.badge}
                  </Badge>
                </div>
              </CardHeader>

              <CardContent className="space-y-5">
                <div
                  className="rounded-3xl border border-primary/10 bg-slate-50 p-5 text-sm leading-7 text-foreground"
                  dangerouslySetInnerHTML={{
                    __html: linkifyText(articleData.sections[section.key] || "No content added."),
                  }}
                />

                <div className="space-y-3">
                  <div className="text-sm font-semibold text-foreground">Attachments</div>
                  {!attachments.length ? (
                    <div className="rounded-2xl border border-dashed border-border bg-background px-4 py-5 text-sm text-muted-foreground">
                      No attachments added.
                    </div>
                  ) : null}

                  {attachments.map((attachment) => {
                    const source = resolveAttachmentUrl(attachment);
                    const isImage = isImageAttachment(source, attachment.type);
                    const isPdf = isPdfAttachment(source, attachment.type);

                    return (
                      <div key={attachment.id} className="space-y-3 rounded-3xl border border-border/80 bg-background p-4 shadow-soft">
                        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                          <div className="flex min-w-0 gap-3">
                            <div className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-2xl border border-border/70 bg-slate-100">
                              {isImage && source ? (
                                <img src={source} alt={attachment.name} className="h-full w-full object-cover" />
                              ) : attachment.url ? (
                                <Link2 className="h-5 w-5 text-muted-foreground" />
                              ) : isPdf ? (
                                <FileText className="h-5 w-5 text-muted-foreground" />
                              ) : (
                                <ImageIcon className="h-5 w-5 text-muted-foreground" />
                              )}
                            </div>

                            <div className="min-w-0">
                              <div className="truncate text-sm font-semibold text-foreground">{attachment.name || "Attachment"}</div>
                              <div className="mt-1 text-xs text-muted-foreground">
                                {attachment.type || "link"}
                                {attachment.size ? ` • ${formatBytes(attachment.size)}` : ""}
                              </div>
                              {attachment.evidencePath ? (
                                <div className="mt-2 truncate text-xs text-muted-foreground">{attachment.evidencePath}</div>
                              ) : attachment.url ? (
                                <div className="mt-2 truncate text-xs text-primary">{attachment.url}</div>
                              ) : null}
                            </div>
                          </div>

                          <div className="flex flex-wrap gap-2 md:justify-end">
                            <Button asChild type="button" variant="outline">
                              <a href={source} target="_blank" rel="noopener noreferrer">
                                <ExternalLink className="h-4 w-4" />
                                Open
                              </a>
                            </Button>
                            {attachment.dataUrl ? (
                              <Button asChild type="button" variant="secondary">
                                <a href={attachment.dataUrl} download={attachment.name || "attachment"}>
                                  Download
                                </a>
                              </Button>
                            ) : null}
                          </div>
                        </div>

                        {isImage && source ? (
                          <details open className="rounded-2xl border border-border/70 bg-white p-3">
                            <summary className="cursor-pointer text-sm font-semibold text-foreground">
                              {attachment.name || "Image attachment"}
                            </summary>
                            <div className="mt-3 flex min-h-[320px] items-center justify-center overflow-hidden rounded-2xl border border-border/70 bg-slate-50 p-3">
                              <img
                                src={source}
                                alt={attachment.name || "Image attachment"}
                                className="max-h-[70vh] w-full object-contain"
                              />
                            </div>
                          </details>
                        ) : null}

                        {isPdf && source ? (
                          <details open className="rounded-2xl border border-border/70 bg-white p-3">
                            <summary className="cursor-pointer text-sm font-semibold text-foreground">
                              {attachment.name || "PDF attachment"}
                            </summary>
                            <div className="mt-3 overflow-hidden rounded-2xl border border-border/70 bg-slate-50">
                              <iframe
                                src={source}
                                title={attachment.name || "PDF attachment"}
                                className="h-[70vh] min-h-[420px] w-full bg-white"
                              />
                            </div>
                          </details>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </SupportLayout>
  );
};

export default KnowledgeBaseArticle;
