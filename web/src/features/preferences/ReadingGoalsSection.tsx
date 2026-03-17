import { useState } from "react";
import {
  Button,
  NumberInput,
  ProgressBar,
  Select,
  SelectItem,
  SkeletonText,
  Tag,
  Tile,
} from "@carbon/react";
import { TrashCan } from "@carbon/icons-react";
import { useReadingGoals, useGoalsProgress, useCreateGoal, useDeleteGoal } from "../../hooks/useUser";
import { QueryErrorNotification } from "../../components/QueryErrorNotification";

const GOAL_TYPES = ["daily", "weekly", "monthly"] as const;
type GoalType = (typeof GOAL_TYPES)[number];

const PERIOD_FOR_TYPE: Record<GoalType, string> = {
  daily: "day",
  weekly: "week",
  monthly: "month",
};

export default function ReadingGoalsSection() {
  const goalsQuery = useReadingGoals();
  const progressQuery = useGoalsProgress();
  const createGoal = useCreateGoal();
  const deleteGoal = useDeleteGoal();

  const [newGoalType, setNewGoalType] = useState<GoalType>("daily");
  const [newTarget, setNewTarget] = useState(5);

  const progressByType = new Map(
    (progressQuery.data ?? []).map((p) => [p.goalType, p]),
  );

  const handleAddGoal = () => {
    createGoal.mutate({
      goalType: newGoalType,
      target: newTarget,
      period: PERIOD_FOR_TYPE[newGoalType],
    });
  };

  const isLoading = (goalsQuery.isLoading && !goalsQuery.data) || (progressQuery.isLoading && !progressQuery.data);

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
            const prog = progressByType.get(goal.goalType);
            const pct = prog ? Math.min(prog.percentage / 100, 1) : 0;
            return (
              <div
                key={goal.goalType}
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
                <div style={{ flex: 1 }}>
                  <ProgressBar
                    label={`${prog?.current ?? goal.currentCount} / ${goal.target}`}
                    value={pct * 100}
                    max={100}
                    size="small"
                    status={goal.isCompleted ? "finished" : "active"}
                  />
                </div>
                <Button
                  kind="ghost"
                  size="sm"
                  iconDescription="Delete goal"
                  renderIcon={TrashCan}
                  hasIconOnly
                  disabled={deleteGoal.isPending}
                  onClick={() => deleteGoal.mutate(goal.goalType)}
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

            <Button
              onClick={handleAddGoal}
              disabled={createGoal.isPending}
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
