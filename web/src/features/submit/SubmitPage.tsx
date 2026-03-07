import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Button,
  InlineLoading,
  InlineNotification,
  ProgressBar,
  TextInput,
  Tile,
} from "@carbon/react";
import { checkDuplicate, fetchRequestStatus, submitUrl } from "../../api/requests";
import { isTerminalStatus, progressFromStatus } from "./status";

export default function SubmitPage() {
  const navigate = useNavigate();
  const [url, setUrl] = useState("");
  const [requestId, setRequestId] = useState<string | null>(null);

  const duplicateQuery = useQuery({
    queryKey: ["duplicate-check", url],
    queryFn: () => checkDuplicate(url.trim()),
    enabled: url.trim().length > 8,
  });

  const submitMutation = useMutation({
    mutationFn: (value: string) => submitUrl(value),
    onSuccess: (result) => {
      setRequestId(result.requestId);
    },
  });

  const statusQuery = useQuery({
    queryKey: ["request-status", requestId],
    queryFn: () => fetchRequestStatus(requestId ?? ""),
    enabled: Boolean(requestId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (!status) return 2500;
      return isTerminalStatus(status) ? false : 2500;
    },
  });

  const progress = useMemo(() => {
    if (!statusQuery.data) return 0;
    return progressFromStatus(statusQuery.data.status, statusQuery.data.progressPct);
  }, [statusQuery.data]);

  const duplicateSummaryId = duplicateQuery.data?.summaryId ?? null;

  return (
    <section className="page-section">
      <h1>Submit URL</h1>
      <Tile>
        <TextInput
          id="submit-url"
          labelText="Article or YouTube URL"
          placeholder="https://example.com/article"
          value={url}
          onChange={(event) => setUrl(event.currentTarget.value)}
        />

        <div className="form-actions">
          <Button
            onClick={() => submitMutation.mutate(url.trim())}
            disabled={!url.trim() || submitMutation.isPending}
          >
            Summarize
          </Button>
          {duplicateSummaryId && (
            <Button kind="ghost" onClick={() => navigate(`/library/${duplicateSummaryId}`)}>
              View existing summary
            </Button>
          )}
        </div>

        {submitMutation.isPending && <InlineLoading description="Submitting URL..." />}

        {submitMutation.error && (
          <InlineNotification
            kind="error"
            title="Submission failed"
            subtitle={submitMutation.error instanceof Error ? submitMutation.error.message : "Unknown error"}
            hideCloseButton
          />
        )}

        {duplicateQuery.data?.isDuplicate && duplicateSummaryId && (
          <InlineNotification
            kind="info"
            title="Duplicate detected"
            subtitle="This URL already has a summary in your library."
            hideCloseButton
          />
        )}

        {requestId && statusQuery.data && (
          <>
            <ProgressBar
              label="Processing status"
              value={progress}
              helperText={`Status: ${statusQuery.data.status}`}
            />
            {statusQuery.data.status === "completed" && statusQuery.data.summaryId && (
              <Button onClick={() => navigate(`/library/${statusQuery.data.summaryId}`)}>
                Open summary
              </Button>
            )}
            {statusQuery.data.status === "failed" && (
              <InlineNotification
                kind="error"
                title="Processing failed"
                subtitle={statusQuery.data.errorMessage ?? "Unknown error"}
                hideCloseButton
              />
            )}
          </>
        )}
      </Tile>
    </section>
  );
}
