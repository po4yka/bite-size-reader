import { useState } from "react";
import {
  Button,
  NumberInput,
  ProgressBar,
  RadioButtonGroup,
  RadioButton,
  Select,
  SelectItem,
  SkeletonText,
  Tag,
  Tile,
} from "@carbon/react";
import { TrashCan } from "@carbon/icons-react";
import { useReadingGoals, useGoalsProgress, useCreateGoal, useDeleteGoal } from "../../hooks/useUser";
import { useTags } from "../../hooks/useTags";
import { useCollectionTree } from "../../hooks/useCollections";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";

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
    <Tile>
      <h3 style={{ marginBottom: "1rem" }}>Reading Goals</h3>

      <QueryErrorNotification error={goalsQuery.error ?? progressQuery.error} title="Failed to load goals" />

      {isLoading && <SkeletonText paragraph lineCount={4} />}

      {goalsQuery.data && (
        <>
          {goalsQuery.data.length === 0 && (
            <p style={{ color: "var(--cds-text-secondary)", marginBottom: "1rem" }}>
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
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.75rem",
                  marginBottom: "0.75rem",
                }}
              >
                <Tag type="blue" size="md" style={{ minWidth: "5rem", justifyContent: "center" }}>
                  {goal.goalType}
                </Tag>
                {goal.scopeType !== "global" && goal.scopeName && (
                  <Tag type="teal" size="md">
                    {goal.scopeType === "tag" ? "Tag" : "Collection"}: {goal.scopeName}
                  </Tag>
                )}
                <div style={{ flex: 1 }}>
                  <ProgressBar
                    label={`${current} / ${target}`}
                    value={pct}
                    max={100}
                    size="small"
                    status={achieved ? "finished" : "active"}
                  />
                </div>
                <Button
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

          <hr style={{ margin: "1rem 0", border: "none", borderTop: "1px solid var(--cds-border-subtle)" }} />

          <p style={{ fontWeight: 600, marginBottom: "0.5rem" }}>Add Goal</p>

          <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-end", flexWrap: "wrap" }}>
            <Select
              id="new-goal-type"
              labelText="Goal type"
              value={newGoalType}
              onChange={(e) => setNewGoalType(e.currentTarget.value as GoalType)}
              style={{ minWidth: "8rem" }}
            >
              {GOAL_TYPES.map((t) => (
                <SelectItem key={t} value={t} text={t.charAt(0).toUpperCase() + t.slice(1)} />
              ))}
            </Select>

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
              <Select
                id="new-goal-scope-tag"
                labelText="Tag"
                value={newScopeId?.toString() ?? ""}
                onChange={(e) => setNewScopeId(e.currentTarget.value ? Number(e.currentTarget.value) : null)}
                style={{ minWidth: "10rem" }}
              >
                <SelectItem value="" text="Select a tag..." />
                {(tagsQuery.data ?? []).map((tag) => (
                  <SelectItem key={tag.id} value={tag.id.toString()} text={tag.name} />
                ))}
              </Select>
            )}

            {newScopeType === "collection" && (
              <Select
                id="new-goal-scope-collection"
                labelText="Collection"
                value={newScopeId?.toString() ?? ""}
                onChange={(e) => setNewScopeId(e.currentTarget.value ? Number(e.currentTarget.value) : null)}
                style={{ minWidth: "10rem" }}
              >
                <SelectItem value="" text="Select a collection..." />
                {(collectionsQuery.data ?? []).map((col) => (
                  <SelectItem key={col.id} value={col.id.toString()} text={col.name} />
                ))}
              </Select>
            )}

            <Button
              onClick={handleAddGoal}
              disabled={createGoal.isPending || !canAdd}
            >
              Add Goal
            </Button>
          </div>

          <QueryErrorNotification error={createGoal.error ?? deleteGoal.error} title="Goal action failed" />
        </>
      )}
    </Tile>
  );
}
