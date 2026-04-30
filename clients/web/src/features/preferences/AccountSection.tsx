import { useState } from "react";
import {
  BracketButton,
  BrutalistCard,
  BrutalistModal,
  MonoInput,
  StatusBadge,
} from "../../design";
import { useDeleteAccount } from "../../hooks/useUser";
import { useAuth } from "../../auth/AuthProvider";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";

const MUTED = "color-mix(in oklch, var(--frost-ink) 55%, transparent)";

export default function AccountSection() {
  const { user } = useAuth();
  const deleteAccount = useDeleteAccount();

  const [modalOpen, setModalOpen] = useState(false);
  const [confirmUsername, setConfirmUsername] = useState("");

  const expectedUsername = user?.username ?? "";
  const canDelete = confirmUsername === expectedUsername && expectedUsername !== "";

  const handleOpenModal = () => {
    setConfirmUsername("");
    setModalOpen(true);
  };

  const handleCloseModal = () => {
    setModalOpen(false);
    setConfirmUsername("");
  };

  const handleDelete = () => {
    if (!canDelete) return;
    deleteAccount.mutate();
  };

  return (
    <BrutalistCard>
      <p
        style={{
          fontFamily: "var(--frost-font-mono)",
          fontSize: "11px",
          fontWeight: 800,
          textTransform: "uppercase",
          letterSpacing: "1px",
          color: MUTED,
          marginBottom: "1rem",
        }}
      >
        § Account
      </p>

      {user && (
        <div style={{ marginBottom: "1rem" }}>
          <p>
            <span style={{ color: MUTED }}>Username: </span>
            <strong>@{user.username}</strong>
          </p>
          <p>
            <span style={{ color: MUTED }}>User ID: </span>
            {user.userId}
          </p>
          <p>
            <span style={{ color: MUTED }}>Member since: </span>
            {new Date(user.createdAt).toLocaleDateString()}
          </p>
        </div>
      )}

      <QueryErrorNotification error={deleteAccount.error} title="Failed to delete account" />

      <BracketButton kind="danger" onClick={handleOpenModal} disabled={deleteAccount.isPending}>
        Delete Account
      </BracketButton>

      <BrutalistModal
        open={modalOpen}
        danger
        modalHeading="Delete Account"
        primaryButtonText="Delete"
        secondaryButtonText="Cancel"
        primaryButtonDisabled={!canDelete || deleteAccount.isPending}
        onRequestClose={handleCloseModal}
        onSecondarySubmit={handleCloseModal}
        onRequestSubmit={handleDelete}
      >
        <StatusBadge severity="warn" title="This action is irreversible">
          All your data, articles, collections, and history will be permanently deleted.
        </StatusBadge>
        <p style={{ marginTop: "1rem", marginBottom: "1rem" }}>
          Type <strong>@{expectedUsername}</strong> to confirm deletion.
        </p>
        <MonoInput
          id="confirm-username"
          labelText="Confirm username"
          placeholder={`@${expectedUsername}`}
          value={confirmUsername}
          onChange={(e) => setConfirmUsername(e.currentTarget.value)}
          invalid={confirmUsername !== "" && !canDelete}
          invalidText="Username does not match"
        />
      </BrutalistModal>
    </BrutalistCard>
  );
}
