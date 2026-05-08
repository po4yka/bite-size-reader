import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  BrutalistModal,
  MonoInput,
  StatusBadge,
} from "../../design";
import { ingestRepository } from "../../api/repositories";

const GITHUB_URL_RE = /^https?:\/\/github\.com\/[a-zA-Z0-9_.-]+\/[a-zA-Z0-9_.-]+\/?$/;

function mapError(status: number | undefined, message: string): string {
  if (status === 400) return "Invalid request — check the URL format.";
  if (status === 404) return "Repository not found on GitHub.";
  if (status === 503)
    return "GitHub integration required — connect first via Preferences > GitHub.";
  if (message) return message;
  return "An unexpected error occurred.";
}

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function IngestRepositoryDialog({ open, onClose }: Props) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [url, setUrl] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  function validate(value: string): boolean {
    if (!value.trim()) {
      setValidationError("Repository URL is required.");
      return false;
    }
    if (!GITHUB_URL_RE.test(value.trim())) {
      setValidationError(
        "Enter a valid GitHub URL: https://github.com/<owner>/<repo>",
      );
      return false;
    }
    setValidationError(null);
    return true;
  }

  async function handleSubmit() {
    if (!validate(url)) return;
    setIsLoading(true);
    setSubmitError(null);
    try {
      const result = await ingestRepository(url.trim());
      await queryClient.invalidateQueries({ queryKey: ["repositories"] });
      handleClose();
      navigate(`/repositories/${result.repository_id}`);
    } catch (err: unknown) {
      const status = (err as { status?: number })?.status;
      const message = (err as { message?: string })?.message ?? "";
      setSubmitError(mapError(status, message));
    } finally {
      setIsLoading(false);
    }
  }

  function handleClose() {
    if (isLoading) return;
    setUrl("");
    setValidationError(null);
    setSubmitError(null);
    onClose();
  }

  return (
    <BrutalistModal
      open={open}
      size="sm"
      modalHeading="Add Repository"
      modalLabel="Repositories"
      primaryButtonText={isLoading ? "Adding…" : "Add"}
      secondaryButtonText="Cancel"
      primaryButtonDisabled={isLoading}
      onRequestSubmit={() => void handleSubmit()}
      onRequestClose={handleClose}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: "var(--frost-line, 16px)",
        }}
      >
        <MonoInput
          id="ingest-url"
          labelText="GitHub repository URL"
          placeholder="https://github.com/owner/repo"
          value={url}
          onChange={(e) => {
            setUrl(e.currentTarget.value);
            if (validationError) validate(e.currentTarget.value);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter") void handleSubmit();
          }}
          invalid={Boolean(validationError)}
          invalidText={validationError ?? undefined}
          disabled={isLoading}
          autoFocus
          aria-label="GitHub repository URL"
        />

        {submitError && (
          <StatusBadge severity="alarm" title="Error">
            {submitError}
          </StatusBadge>
        )}
      </div>
    </BrutalistModal>
  );
}
