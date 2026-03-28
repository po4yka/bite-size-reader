import { useState } from "react";
import {
  DatePicker,
  DatePickerInput,
  FilterableMultiSelect,
  InlineLoading,
  InlineNotification,
  Modal,
  NumberInput,
  TextInput,
} from "@carbon/react";
import { useDigestChannels, useCreateCustomDigest } from "../../hooks/useDigest";

interface Props {
  open: boolean;
  onClose: () => void;
}

interface ChannelItem {
  id: number;
  label: string;
}

export function CustomDigestCreateModal({ open, onClose }: Props) {
  const [title, setTitle] = useState("");
  const [selectedChannels, setSelectedChannels] = useState<ChannelItem[]>([]);
  const [maxPosts, setMaxPosts] = useState(20);
  const [dateFrom, setDateFrom] = useState<string | undefined>(undefined);
  const [dateTo, setDateTo] = useState<string | undefined>(undefined);

  const channelsQuery = useDigestChannels();
  const createMutation = useCreateCustomDigest();

  const channelItems: ChannelItem[] = (channelsQuery.data?.channels ?? []).map((c) => ({
    id: c.id,
    label: c.title ? `${c.title} (@${c.username})` : `@${c.username}`,
  }));

  function handleClose() {
    setTitle("");
    setSelectedChannels([]);
    setMaxPosts(20);
    setDateFrom(undefined);
    setDateTo(undefined);
    createMutation.reset();
    onClose();
  }

  function handleCreate() {
    if (!title.trim() || selectedChannels.length === 0) return;
    createMutation.mutate(
      {
        title: title.trim(),
        channelIds: selectedChannels.map((c) => c.id),
        maxPosts,
        dateFrom: dateFrom ?? undefined,
        dateTo: dateTo ?? undefined,
      },
      {
        onSuccess: () => {
          handleClose();
        },
      },
    );
  }

  const canCreate = title.trim().length > 0 && selectedChannels.length > 0 && !createMutation.isPending;

  return (
    <Modal
      open={open}
      modalHeading="Create Custom Digest"
      primaryButtonText={createMutation.isPending ? "Creating..." : "Create"}
      secondaryButtonText="Cancel"
      primaryButtonDisabled={!canCreate}
      onRequestSubmit={handleCreate}
      onRequestClose={handleClose}
      onSecondarySubmit={handleClose}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <TextInput
          id="custom-digest-title"
          labelText="Digest title"
          placeholder="My custom digest"
          value={title}
          onChange={(e) => setTitle(e.currentTarget.value)}
          disabled={createMutation.isPending}
        />

        {channelsQuery.isLoading && <InlineLoading description="Loading channels..." />}

        {!channelsQuery.isLoading && (
          <FilterableMultiSelect
            id="custom-digest-channels"
            titleText="Channels"
            placeholder="Select channels"
            items={channelItems}
            itemToString={(item: ChannelItem | null) => item?.label ?? ""}
            selectedItems={selectedChannels}
            onChange={(data: { selectedItems: ChannelItem[] | null }) => {
              setSelectedChannels(data.selectedItems ?? []);
            }}
            disabled={createMutation.isPending}
          />
        )}

        <DatePicker
          datePickerType="range"
          onChange={(dates: Date[]) => {
            const [from, to] = dates;
            setDateFrom(from ? from.toISOString().split("T")[0] : undefined);
            setDateTo(to ? to.toISOString().split("T")[0] : undefined);
          }}
        >
          <DatePickerInput
            id="custom-digest-date-from"
            placeholder="mm/dd/yyyy"
            labelText="Date from (optional)"
            disabled={createMutation.isPending}
          />
          <DatePickerInput
            id="custom-digest-date-to"
            placeholder="mm/dd/yyyy"
            labelText="Date to (optional)"
            disabled={createMutation.isPending}
          />
        </DatePicker>

        <NumberInput
          id="custom-digest-max-posts"
          label="Max posts"
          value={maxPosts}
          min={5}
          max={100}
          onChange={(_event: unknown, { value }: { value: string | number }) => {
            const n = Number(value);
            if (Number.isFinite(n)) setMaxPosts(n);
          }}
          disabled={createMutation.isPending}
        />

        {createMutation.isError && (
          <InlineNotification
            kind="error"
            title="Failed to create digest"
            subtitle={
              createMutation.error instanceof Error
                ? createMutation.error.message
                : "Unknown error"
            }
            hideCloseButton
          />
        )}
      </div>
    </Modal>
  );
}
