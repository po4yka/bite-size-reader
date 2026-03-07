import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  DataTable,
  InlineLoading,
  InlineNotification,
  NumberInput,
  Pagination,
  Select,
  SelectItem,
  Tab,
  TabList,
  TabPanel,
  TabPanels,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableHeader,
  TableRow,
  TextInput,
  Theme,
  TimePicker,
  Tile,
} from "@carbon/react";
import { useAuth } from "../../auth/AuthProvider";
import {
  fetchDigestChannels,
  fetchDigestHistory,
  fetchDigestPreferences,
  subscribeDigestChannel,
  triggerDigestNow,
  triggerSingleChannelDigest,
  unsubscribeDigestChannel,
  updateDigestPreferences,
} from "../../api/digest";

const HISTORY_PAGE_SIZE = 20;

function DigestUnavailableNotice() {
  return (
    <InlineNotification
      kind="warning"
      title="Digest requires Telegram WebApp context"
      subtitle="Digest endpoints require Telegram initData, so this section is available when opened from Telegram Mini App context."
      hideCloseButton
    />
  );
}

function ChannelsTab({ isOwner }: { isOwner: boolean }) {
  const queryClient = useQueryClient();
  const [channelInput, setChannelInput] = useState("");
  const [ownerChannel, setOwnerChannel] = useState("");

  const channelsQuery = useQuery({
    queryKey: ["digest-channels"],
    queryFn: fetchDigestChannels,
  });

  const subscribeMutation = useMutation({
    mutationFn: (username: string) => subscribeDigestChannel(username),
    onSuccess: () => {
      setChannelInput("");
      void queryClient.invalidateQueries({ queryKey: ["digest-channels"] });
    },
  });

  const unsubscribeMutation = useMutation({
    mutationFn: (username: string) => unsubscribeDigestChannel(username),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["digest-channels"] });
    },
  });

  const triggerMutation = useMutation({
    mutationFn: triggerDigestNow,
  });

  const ownerTriggerMutation = useMutation({
    mutationFn: (username: string) => triggerSingleChannelDigest(username),
    onSuccess: () => setOwnerChannel(""),
  });

  const headers = [
    { key: "username", header: "Channel" },
    { key: "title", header: "Title" },
    { key: "fetchErrorCount", header: "Errors" },
    { key: "createdAt", header: "Subscribed" },
    { key: "actions", header: "Actions" },
  ];

  const rows = useMemo(
    () =>
      (channelsQuery.data?.channels ?? []).map((channel) => ({
        id: String(channel.id),
        username: `@${channel.username}`,
        title: channel.title ?? "-",
        fetchErrorCount: channel.fetchErrorCount,
        createdAt: new Date(channel.createdAt).toLocaleString(),
        actions: channel.username,
      })),
    [channelsQuery.data?.channels],
  );

  return (
    <div className="page-section">
      <Tile>
        <h3>Subscriptions</h3>

        <div className="form-actions">
          <TextInput
            id="digest-subscribe-input"
            labelText="Channel username"
            placeholder="@channel_name or t.me/channel"
            value={channelInput}
            onChange={(event) => setChannelInput(event.currentTarget.value)}
          />
          <Button
            kind="secondary"
            disabled={!channelInput.trim() || subscribeMutation.isPending}
            onClick={() => subscribeMutation.mutate(channelInput.trim())}
          >
            Subscribe
          </Button>
        </div>

        {channelsQuery.isLoading && <InlineLoading description="Loading channels..." />}

        {(channelsQuery.error || subscribeMutation.error || unsubscribeMutation.error) && (
          <InlineNotification
            kind="error"
            title="Digest channel operation failed"
            subtitle={
              (channelsQuery.error || subscribeMutation.error || unsubscribeMutation.error) instanceof Error
                ? ((channelsQuery.error || subscribeMutation.error || unsubscribeMutation.error) as Error).message
                : "Unknown error"
            }
            hideCloseButton
          />
        )}

        {channelsQuery.data && (
          <p className="muted">
            {channelsQuery.data.unlimitedChannels || channelsQuery.data.maxChannels == null
              ? `${channelsQuery.data.activeCount} channels subscribed`
              : `${channelsQuery.data.activeCount}/${channelsQuery.data.maxChannels} slots used`}
          </p>
        )}

        <DataTable rows={rows} headers={headers}>
          {({ rows, headers, getHeaderProps, getRowProps, getTableProps }) => (
            <TableContainer title="Digest channels">
              <Table {...getTableProps()}>
                <TableHead>
                  <TableRow>
                    {headers.map((header) => (
                      <TableHeader {...getHeaderProps({ header })}>{header.header}</TableHeader>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rows.map((row) => {
                    const username = row.cells.find((cell) => cell.info.header === "Actions")?.value as string;
                    return (
                      <TableRow {...getRowProps({ row })}>
                        {row.cells.map((cell) => {
                          if (cell.info.header === "Actions") {
                            return (
                              <TableCell key={cell.id}>
                                <Button
                                  kind="danger--ghost"
                                  size="sm"
                                  disabled={unsubscribeMutation.isPending}
                                  onClick={() => unsubscribeMutation.mutate(username)}
                                >
                                  Remove
                                </Button>
                              </TableCell>
                            );
                          }
                          return <TableCell key={cell.id}>{String(cell.value)}</TableCell>;
                        })}
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </DataTable>

        <div className="form-actions">
          <Button
            disabled={(channelsQuery.data?.activeCount ?? 0) === 0 || triggerMutation.isPending}
            onClick={() => triggerMutation.mutate()}
          >
            Generate Digest Now
          </Button>
          {triggerMutation.isSuccess && (
            <InlineNotification
              kind="success"
              title="Digest queued"
              subtitle={`Correlation ID: ${triggerMutation.data.correlationId}`}
              hideCloseButton
            />
          )}
        </div>

        {isOwner && (
          <>
            <h4>Owner: Trigger single-channel digest</h4>
            <div className="form-actions">
              <TextInput
                id="owner-channel-input"
                labelText="Channel"
                placeholder="@channel_name"
                value={ownerChannel}
                onChange={(event) => setOwnerChannel(event.currentTarget.value)}
              />
              <Button
                kind="tertiary"
                disabled={!ownerChannel.trim() || ownerTriggerMutation.isPending}
                onClick={() => ownerTriggerMutation.mutate(ownerChannel.trim())}
              >
                Trigger Channel Digest
              </Button>
            </div>

            {ownerTriggerMutation.error && (
              <InlineNotification
                kind="error"
                title="Single-channel trigger failed"
                subtitle={
                  ownerTriggerMutation.error instanceof Error
                    ? ownerTriggerMutation.error.message
                    : "Unknown error"
                }
                hideCloseButton
              />
            )}

            {ownerTriggerMutation.isSuccess && (
              <InlineNotification
                kind="success"
                title="Single-channel digest queued"
                subtitle={`Channel: @${ownerTriggerMutation.data.channel}`}
                hideCloseButton
              />
            )}
          </>
        )}
      </Tile>
    </div>
  );
}

function PreferencesTab() {
  const queryClient = useQueryClient();

  const preferencesQuery = useQuery({
    queryKey: ["digest-preferences"],
    queryFn: fetchDigestPreferences,
  });

  const [deliveryTime, setDeliveryTime] = useState("09:00");
  const [timezone, setTimezone] = useState("UTC");
  const [hoursLookback, setHoursLookback] = useState(24);
  const [maxPostsPerDigest, setMaxPostsPerDigest] = useState(20);
  const [minRelevanceScore, setMinRelevanceScore] = useState(0.3);

  useEffect(() => {
    if (!preferencesQuery.data) return;
    setDeliveryTime(preferencesQuery.data.deliveryTime);
    setTimezone(preferencesQuery.data.timezone);
    setHoursLookback(preferencesQuery.data.hoursLookback);
    setMaxPostsPerDigest(preferencesQuery.data.maxPostsPerDigest);
    setMinRelevanceScore(preferencesQuery.data.minRelevanceScore);
  }, [preferencesQuery.data]);

  const saveMutation = useMutation({
    mutationFn: () =>
      updateDigestPreferences({
        delivery_time: deliveryTime,
        timezone,
        hours_lookback: hoursLookback,
        max_posts_per_digest: maxPostsPerDigest,
        min_relevance_score: minRelevanceScore,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["digest-preferences"] });
    },
  });

  const data = preferencesQuery.data;

  return (
    <div className="page-section">
      <Tile>
        <h3>Digest preferences</h3>

        {preferencesQuery.isLoading && <InlineLoading description="Loading preferences..." />}

        {(preferencesQuery.error || saveMutation.error) && (
          <InlineNotification
            kind="error"
            title="Digest preference operation failed"
            subtitle={
              (preferencesQuery.error || saveMutation.error) instanceof Error
                ? ((preferencesQuery.error || saveMutation.error) as Error).message
                : "Unknown error"
            }
            hideCloseButton
          />
        )}

        {data && (
          <div className="digest-form-grid">
            <TimePicker
              id="digest-delivery-time"
              labelText={`Delivery time (${data.deliveryTimeSource})`}
              value={deliveryTime}
              onChange={(event) => setDeliveryTime(event.currentTarget.value)}
            />

            <Select
              id="digest-timezone"
              labelText={`Timezone (${data.timezoneSource})`}
              value={timezone}
              onChange={(event) => setTimezone(event.currentTarget.value)}
            >
              <SelectItem text="UTC" value="UTC" />
              <SelectItem text="Europe/London" value="Europe/London" />
              <SelectItem text="Europe/Moscow" value="Europe/Moscow" />
              <SelectItem text="US/Eastern" value="US/Eastern" />
              <SelectItem text="US/Pacific" value="US/Pacific" />
              <SelectItem text="Asia/Tokyo" value="Asia/Tokyo" />
              <SelectItem text="Asia/Shanghai" value="Asia/Shanghai" />
            </Select>

            <NumberInput
              id="digest-hours-lookback"
              label={`Hours lookback (${data.hoursLookbackSource})`}
              min={1}
              max={168}
              value={hoursLookback}
              onChange={(_, state) => setHoursLookback(Number(state.value || hoursLookback))}
            />

            <NumberInput
              id="digest-max-posts"
              label={`Max posts per digest (${data.maxPostsPerDigestSource})`}
              min={1}
              max={100}
              value={maxPostsPerDigest}
              onChange={(_, state) => setMaxPostsPerDigest(Number(state.value || maxPostsPerDigest))}
            />

            <NumberInput
              id="digest-min-relevance"
              label={`Min relevance score (${data.minRelevanceScoreSource})`}
              min={0}
              max={1}
              step={0.05}
              value={minRelevanceScore}
              onChange={(_, state) => {
                const value = Number(state.value);
                if (Number.isFinite(value)) {
                  setMinRelevanceScore(Math.max(0, Math.min(1, value)));
                }
              }}
            />
          </div>
        )}

        <div className="form-actions">
          <Button disabled={saveMutation.isPending} onClick={() => saveMutation.mutate()}>
            Save Digest Preferences
          </Button>

          {saveMutation.isSuccess && (
            <InlineNotification
              kind="success"
              title="Preferences saved"
              subtitle="Digest settings were updated successfully."
              hideCloseButton
            />
          )}
        </div>
      </Tile>
    </div>
  );
}

function HistoryTab() {
  const [page, setPage] = useState(1);

  const historyQuery = useQuery({
    queryKey: ["digest-history", page],
    queryFn: () => fetchDigestHistory(HISTORY_PAGE_SIZE, (page - 1) * HISTORY_PAGE_SIZE),
  });

  const rows = useMemo(
    () =>
      (historyQuery.data?.deliveries ?? []).map((entry) => ({
        id: String(entry.id),
        deliveredAt: new Date(entry.deliveredAt).toLocaleString(),
        postCount: entry.postCount,
        channelCount: entry.channelCount,
        digestType: entry.digestType,
      })),
    [historyQuery.data?.deliveries],
  );

  const headers = [
    { key: "deliveredAt", header: "Delivered" },
    { key: "postCount", header: "Posts" },
    { key: "channelCount", header: "Channels" },
    { key: "digestType", header: "Type" },
  ];

  return (
    <div className="page-section">
      <Tile>
        <h3>Digest history</h3>

        {historyQuery.isLoading && <InlineLoading description="Loading digest history..." />}

        {historyQuery.error && (
          <InlineNotification
            kind="error"
            title="Failed to load digest history"
            subtitle={historyQuery.error instanceof Error ? historyQuery.error.message : "Unknown error"}
            hideCloseButton
          />
        )}

        <DataTable rows={rows} headers={headers}>
          {({ rows, headers, getHeaderProps, getRowProps, getTableProps }) => (
            <TableContainer title="Digest deliveries">
              <Table {...getTableProps()}>
                <TableHead>
                  <TableRow>
                    {headers.map((header) => (
                      <TableHeader {...getHeaderProps({ header })}>{header.header}</TableHeader>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rows.map((row) => (
                    <TableRow {...getRowProps({ row })}>
                      {row.cells.map((cell) => (
                        <TableCell key={cell.id}>{String(cell.value)}</TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </DataTable>

        {historyQuery.data && (
          <Pagination
            page={page}
            pageSize={HISTORY_PAGE_SIZE}
            pageSizes={[HISTORY_PAGE_SIZE]}
            totalItems={historyQuery.data.total}
            onChange={(event) => setPage(event.page)}
          />
        )}
      </Tile>
    </div>
  );
}

export default function DigestPage() {
  const { mode, user } = useAuth();

  return (
    <Theme theme="white">
      <section className="page-section">
        <h1>Digest</h1>

        {mode !== "telegram-webapp" && <DigestUnavailableNotice />}

        {mode === "telegram-webapp" && (
          <Tabs>
            <TabList aria-label="Digest tabs" contained>
              <Tab>Channels</Tab>
              <Tab>Preferences</Tab>
              <Tab>History</Tab>
            </TabList>
            <TabPanels>
              <TabPanel>
                <ChannelsTab isOwner={Boolean(user?.isOwner)} />
              </TabPanel>
              <TabPanel>
                <PreferencesTab />
              </TabPanel>
              <TabPanel>
                <HistoryTab />
              </TabPanel>
            </TabPanels>
          </Tabs>
        )}
      </section>
    </Theme>
  );
}
