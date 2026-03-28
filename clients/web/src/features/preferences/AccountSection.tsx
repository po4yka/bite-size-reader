import { useState } from "react";
import {
  Button,
  InlineNotification,
  Modal,
  TextInput,
  Tile,
} from "@carbon/react";
import { useDeleteAccount } from "../../hooks/useUser";
import { useAuth } from "../../auth/AuthProvider";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";

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
    <Tile>
      <h3 style={{ marginBottom: "1rem" }}>Account</h3>

      {user && (
        <div style={{ marginBottom: "1rem" }}>
          <p>
            <span style={{ color: "var(--cds-text-secondary)" }}>Username: </span>
            <strong>@{user.username}</strong>
          </p>
          <p>
            <span style={{ color: "var(--cds-text-secondary)" }}>User ID: </span>
            {user.userId}
          </p>
          <p>
            <span style={{ color: "var(--cds-text-secondary)" }}>Member since: </span>
            {new Date(user.createdAt).toLocaleDateString()}
          </p>
        </div>
      )}

      <QueryErrorNotification error={deleteAccount.error} title="Failed to delete account" />

      <Button kind="danger" onClick={handleOpenModal} disabled={deleteAccount.isPending}>
        Delete Account
      </Button>

      <Modal
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
        <InlineNotification
          kind="warning"
          title="This action is irreversible"
          subtitle="All your data, articles, collections, and history will be permanently deleted."
          hideCloseButton
          style={{ marginBottom: "1rem" }}
        />
        <p style={{ marginBottom: "1rem" }}>
          Type <strong>@{expectedUsername}</strong> to confirm deletion.
        </p>
        <TextInput
          id="confirm-username"
          labelText="Confirm username"
          placeholder={`@${expectedUsername}`}
          value={confirmUsername}
          onChange={(e) => setConfirmUsername(e.currentTarget.value)}
          invalid={confirmUsername !== "" && !canDelete}
          invalidText="Username does not match"
        />
      </Modal>
    </Tile>
  );
}
