import { useState } from "react";
import {
  BracketButton,
  BrutalistCard,
  BrutalistSkeletonText,
  MonoProgressBar,
  MonoSelect,
  MonoSelectItem,
  NumberInput,
  RadioButton,
  RadioButtonGroup,
  Tag,
  TrashCan,
} from "../../design";
import { useReadingGoals, useGoalsProgress, useCreateGoal, useDeleteGoal } from "../../hooks/useUser";
import { useTags } from "../../hooks/useTags";
import { useCollectionTree } from "../../hooks/useCollections";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";

const MUTED = "color-mix(in oklch, var(--frost-ink) 55%, transparent)";

const GOAL_TYPES = ["daily", "weekly", "monthly"] as const;
type GoalType = (typeof GOAL_TYPES)[number];
type ScopeType = "global" | "tag" | "collection";

export default function ReadingGoalsSection() {
  const goalsQuery = useReadingGoals();
  const progressQuery = useGoalsProgress();
  const createGoal = useCreateGoal();
  const deleteGoal = useDeleteGoal();
  const tagsQuery = useTags();
  const collectionsQuery = useCollectionTree();

  const [newGoalType, setNewGoalType] = useState<GoalType>("daily");
  const [newTarget, setNewTarget] = useState(5);
  const [newScopeType, setNewScopeType] = useState<ScopeType>("global");
  const [newScopeId, setNewScopeId] = useState<number | null>(null);

  const progressByKey = new Map(
    (progressQuery.data ?? []).map((p) => {
      const key = `${p.goalType}:${p.scopeType ?? "global"}:${p.scopeId ?? ""}`;
      return [key, p];
    }),
  );

  const handleAddGoal = () => {
    createGoal.mutate({
      goalType: newGoalType,
      targetCount: newTarget,
      scopeType: newScopeType,
      scopeId: newScopeType === "global" ? null : newScopeId,
    });
  };

  const handleScopeTypeChange = (value: string | number | undefined) => {
    if (typeof value === "string") {
      setNewScopeType(value as ScopeType);
      setNewScopeId(null);
    }
  };

  const isLoading = (goalsQuery.isLoading && !goalsQuery.data) || (progressQuery.isLoading && !progressQuery.data);

  const canAdd =
    newScopeType === "global" || (newScopeId !== null && newScopeId > 0);

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
        § Reading Goals
      </p>

      <QueryErrorNotification error={goalsQuery.error ?? progressQuery.error} title="Failed to load goals" />

      {isLoading && <BrutalistSkeletonText paragraph lineCount={4} />}

      {goalsQuery.data && (
        <>
          {goalsQuery.data.length === 0 && (
            <p style={{ color: MUTED, marginBottom: "1rem" }}>
              No goals set yet.
            </p>
          )}

          {goalsQuery.data.map((goal) => {
            const progressKey = `${goal.goalType}:${goal.scopeType ?? "global"}:${goal.scopeId ?? ""}`;
            const prog = progressByKey.get(progressKey);
            const current = prog?.currentCount ?? 0;
            const target = goal.targetCount;
            const pct = target > 0 ? Math.min((current / target) * 100, 100) : 0;
            const achieved = prog?.achieved ?? false;

            return (
              <div
                key={goal.id}
                className="reading-goal-row"
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.75rem",
                  marginBottom: "0.75rem",
                }}
              >
                <Tag size="md" style={{ minWidth: "5rem", justifyContent: "center" }}>
                  {goal.goalType}
                </Tag>
                {goal.scopeType !== "global" && goal.scopeName && (
                  <Tag size="md">
                    {goal.scopeType === "tag" ? "Tag" : "Collection"}: {goal.scopeName}
                  </Tag>
                )}
                <div style={{ flex: 1 }}>
                  <MonoProgressBar
                    label={`${current} / ${target}`}
                    value={pct}
                    max={100}
                    status={achieved ? "finished" : "active"}
                  />
                </div>
                <BracketButton
                  kind="ghost"
                  size="sm"
                  iconDescription="Delete goal"
                  renderIcon={TrashCan}
                  hasIconOnly
                  disabled={deleteGoal.isPending}
                  onClick={() =>
                    deleteGoal.mutate({
                      goalType: goal.goalType,
                      goalId: goal.scopeType !== "global" ? goal.id : undefined,
                    })
                  }
                />
              </div>
            );
          })}

          <hr style={{ margin: "1rem 0", border: "none", borderTop: "1px solid color-mix(in oklch, var(--frost-ink) 25%, transparent)" }} />

          <p style={{ fontWeight: 600, marginBottom: "0.5rem" }}>Add Goal</p>

          <div className="reading-goals-form" style={{ display: "flex", gap: "0.75rem", alignItems: "flex-end", flexWrap: "wrap" }}>
            <MonoSelect
              id="new-goal-type"
              labelText="Goal type"
              value={newGoalType}
              onChange={(e) => setNewGoalType(e.currentTarget.value as GoalType)}
              style={{ minWidth: "8rem" }}
            >
              {GOAL_TYPES.map((t) => (
                <MonoSelectItem key={t} value={t} text={t.charAt(0).toUpperCase() + t.slice(1)} />
              ))}
            </MonoSelect>

            <NumberInput
              id="new-goal-target"
              label="Target (articles)"
              min={1}
              max={100}
              value={newTarget}
              onChange={(_, { value }) => setNewTarget(Number(value))}
            />

            <RadioButtonGroup
              legendText="Scope"
              name="goal-scope-type"
              valueSelected={newScopeType}
              onChange={handleScopeTypeChange}
              orientation="horizontal"
            >
              <RadioButton labelText="Global" value="global" id="scope-global" />
              <RadioButton labelText="Tag" value="tag" id="scope-tag" />
              <RadioButton labelText="Collection" value="collection" id="scope-collection" />
            </RadioButtonGroup>

            {newScopeType === "tag" && (
              <MonoSelect
                id="new-goal-scope-tag"
                labelText="Tag"
                value={newScopeId?.toString() ?? ""}
                onChange={(e) => setNewScopeId(e.currentTarget.value ? Number(e.currentTarget.value) : null)}
                style={{ minWidth: "10rem" }}
              >
                <MonoSelectItem value="" text="Select a tag..." />
                {(tagsQuery.data ?? []).map((tag) => (
                  <MonoSelectItem key={tag.id} value={tag.id.toString()} text={tag.name} />
                ))}
              </MonoSelect>
            )}

            {newScopeType === "collection" && (
              <MonoSelect
                id="new-goal-scope-collection"
                labelText="Collection"
                value={newScopeId?.toString() ?? ""}
                onChange={(e) => setNewScopeId(e.currentTarget.value ? Number(e.currentTarget.value) : null)}
                style={{ minWidth: "10rem" }}
              >
                <MonoSelectItem value="" text="Select a collection..." />
                {(collectionsQuery.data ?? []).map((col) => (
                  <MonoSelectItem key={col.id} value={col.id.toString()} text={col.name} />
                ))}
              </MonoSelect>
            )}

            <BracketButton
              onClick={handleAddGoal}
              disabled={createGoal.isPending || !canAdd}
            >
              Add Goal
            </BracketButton>
          </div>

          <QueryErrorNotification error={createGoal.error ?? deleteGoal.error} title="Goal action failed" />
        </>
      )}
    </BrutalistCard>
  );
}
