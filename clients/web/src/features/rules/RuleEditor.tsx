import { useState } from "react";
import {
  Button,
  Modal,
  NumberInput,
  RadioButton,
  RadioButtonGroup,
  Select,
  SelectItem,
  TextInput,
  Toggle,
  Add,
  TrashCan,
} from "../../design";
import type { Rule, Condition, Action, CreateRulePayload, UpdateRulePayload } from "../../api/rules";
import {
  RULE_EVENT_TYPES,
  CONDITION_TYPES,
  CONDITION_OPERATORS,
  NUMERIC_CONDITION_TYPES,
  ACTION_TYPES,
} from "../../api/rules";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function emptyCondition(): Condition {
  return { type: CONDITION_TYPES[0], operator: "equals", value: "" };
}

function emptyAction(): Action {
  return { type: ACTION_TYPES[0], params: {} };
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ConditionRow({
  condition,
  index,
  onChange,
  onRemove,
}: {
  condition: Condition;
  index: number;
  onChange: (index: number, updated: Condition) => void;
  onRemove: (index: number) => void;
}) {
  const operators = CONDITION_OPERATORS[condition.type] ?? ["equals"];
  const isNumeric = NUMERIC_CONDITION_TYPES.has(condition.type);

  return (
    <div style={{ display: "flex", gap: "0.5rem", alignItems: "flex-end", marginBottom: "0.5rem" }}>
      <Select
        id={`cond-type-${index}`}
        labelText="Type"
        value={condition.type}
        onChange={(e) => {
          const newType = e.target.value;
          const newOps = CONDITION_OPERATORS[newType] ?? ["equals"];
          onChange(index, { ...condition, type: newType, operator: newOps[0], value: "" });
        }}
      >
        {CONDITION_TYPES.map((t) => (
          <SelectItem key={t} value={t} text={t} />
        ))}
      </Select>
      <Select
        id={`cond-op-${index}`}
        labelText="Operator"
        value={condition.operator}
        onChange={(e) => onChange(index, { ...condition, operator: e.target.value })}
      >
        {operators.map((op) => (
          <SelectItem key={op} value={op} text={op} />
        ))}
      </Select>
      {isNumeric ? (
        <NumberInput
          id={`cond-val-${index}`}
          label="Value"
          value={typeof condition.value === "number" ? condition.value : 0}
          onChange={(_e, { value }: { value: string | number }) =>
            onChange(index, { ...condition, value: Number(value) })
          }
          min={0}
          step={1}
          hideSteppers
        />
      ) : (
        <TextInput
          id={`cond-val-${index}`}
          labelText="Value"
          value={String(condition.value)}
          onChange={(e) => onChange(index, { ...condition, value: e.currentTarget.value })}
          placeholder="value"
        />
      )}
      <Button
        kind="danger--ghost"
        size="sm"
        hasIconOnly
        renderIcon={TrashCan}
        iconDescription="Remove condition"
        onClick={() => onRemove(index)}
      />
    </div>
  );
}

function ActionRow({
  action,
  index,
  onChange,
  onRemove,
}: {
  action: Action;
  index: number;
  onChange: (index: number, updated: Action) => void;
  onRemove: (index: number) => void;
}) {
  const actionType = action.type;

  function renderParamInput() {
    switch (actionType) {
      case "add_tag":
      case "remove_tag":
        return (
          <TextInput
            id={`action-param-${index}`}
            labelText="Tag name"
            value={String(action.params.tag_name ?? "")}
            onChange={(e) =>
              onChange(index, { ...action, params: { ...action.params, tag_name: e.currentTarget.value } })
            }
            placeholder="tag name"
          />
        );
      case "add_to_collection":
        return (
          <NumberInput
            id={`action-param-${index}`}
            label="Collection ID"
            value={Number(action.params.collection_id ?? 0)}
            onChange={(_e, { value }: { value: string | number }) =>
              onChange(index, { ...action, params: { ...action.params, collection_id: Number(value) } })
            }
            min={1}
            step={1}
            hideSteppers
          />
        );
      case "set_favorite":
        return (
          <Toggle
            id={`action-param-${index}`}
            labelText="Favorite"
            labelA="Off"
            labelB="On"
            toggled={Boolean(action.params.favorite ?? false)}
            onToggle={(checked: boolean) =>
              onChange(index, { ...action, params: { ...action.params, favorite: checked } })
            }
          />
        );
      default:
        return null;
    }
  }

  return (
    <div style={{ display: "flex", gap: "0.5rem", alignItems: "flex-end", marginBottom: "0.5rem" }}>
      <Select
        id={`action-type-${index}`}
        labelText="Action"
        value={action.type}
        onChange={(e) => onChange(index, { type: e.target.value, params: {} })}
      >
        {ACTION_TYPES.map((t) => (
          <SelectItem key={t} value={t} text={t} />
        ))}
      </Select>
      {renderParamInput()}
      <Button
        kind="danger--ghost"
        size="sm"
        hasIconOnly
        renderIcon={TrashCan}
        iconDescription="Remove action"
        onClick={() => onRemove(index)}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main editor
// ---------------------------------------------------------------------------

interface RuleEditorProps {
  open: boolean;
  rule: Rule | null; // null = create mode
  onClose: () => void;
  onSave: (payload: CreateRulePayload | UpdateRulePayload) => void;
  onTest?: (ruleId: number, summaryId: number) => void;
  isSaving: boolean;
}

export default function RuleEditor({ open, rule, onClose, onSave, onTest, isSaving }: RuleEditorProps) {
  const isEdit = rule != null;

  const [name, setName] = useState(rule?.name ?? "");
  const [description, setDescription] = useState(rule?.description ?? "");
  const [eventType, setEventType] = useState(rule?.eventType ?? RULE_EVENT_TYPES[0]);
  const [matchMode, setMatchMode] = useState(rule?.matchMode ?? "all");
  const [conditions, setConditions] = useState<Condition[]>(rule?.conditions ?? [emptyCondition()]);
  const [actions, setActions] = useState<Action[]>(rule?.actions ?? [emptyAction()]);
  const [priority, setPriority] = useState(rule?.priority ?? 0);
  const [testSummaryId, setTestSummaryId] = useState("");
  const [testModalOpen, setTestModalOpen] = useState(false);

  // Reset state when the modal opens with a different rule
  // This is handled by the parent unmounting/remounting the component via key prop

  function handleConditionChange(index: number, updated: Condition) {
    setConditions((prev) => prev.map((c, i) => (i === index ? updated : c)));
  }

  function handleConditionRemove(index: number) {
    setConditions((prev) => prev.filter((_, i) => i !== index));
  }

  function handleActionChange(index: number, updated: Action) {
    setActions((prev) => prev.map((a, i) => (i === index ? updated : a)));
  }

  function handleActionRemove(index: number) {
    setActions((prev) => prev.filter((_, i) => i !== index));
  }

  function handleSubmit() {
    const payload: CreateRulePayload = {
      name: name.trim(),
      description: description.trim() || null,
      eventType,
      matchMode,
      conditions,
      actions,
      priority,
    };
    onSave(payload);
  }

  function handleTestClick() {
    if (!rule || !onTest) return;
    const sid = parseInt(testSummaryId, 10);
    if (isNaN(sid) || sid <= 0) return;
    onTest(rule.id, sid);
    setTestModalOpen(false);
    setTestSummaryId("");
  }

  const canSave = name.trim().length > 0 && conditions.length > 0 && actions.length > 0;

  return (
    <>
      <Modal
        open={open}
        modalHeading={isEdit ? "Edit rule" : "Create rule"}
        primaryButtonText={isSaving ? "Saving..." : "Save"}
        secondaryButtonText="Cancel"
        primaryButtonDisabled={!canSave || isSaving}
        onRequestClose={() => {
          if (!isSaving) onClose();
        }}
        onRequestSubmit={handleSubmit}
        size="md"
      >
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <TextInput
            id="rule-name"
            labelText="Name"
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
            placeholder="My rule"
          />
          <TextInput
            id="rule-description"
            labelText="Description (optional)"
            value={description}
            onChange={(e) => setDescription(e.currentTarget.value)}
            placeholder="What this rule does"
          />
          <Select
            id="rule-event-type"
            labelText="Event type"
            value={eventType}
            onChange={(e) => setEventType(e.target.value)}
          >
            {RULE_EVENT_TYPES.map((evt) => (
              <SelectItem key={evt} value={evt} text={evt} />
            ))}
          </Select>
          <RadioButtonGroup
            legendText="Match mode"
            name="match-mode"
            valueSelected={matchMode}
            onChange={(value) => setMatchMode(value as string)}
          >
            <RadioButton labelText="All conditions" value="all" id="match-all" />
            <RadioButton labelText="Any condition" value="any" id="match-any" />
          </RadioButtonGroup>

          {/* Conditions */}
          <fieldset className="rtk-fieldset">
            <legend className="rtk-label">Conditions</legend>
            {conditions.map((cond, i) => (
              <ConditionRow
                key={i}
                condition={cond}
                index={i}
                onChange={handleConditionChange}
                onRemove={handleConditionRemove}
              />
            ))}
            <Button
              kind="ghost"
              size="sm"
              renderIcon={Add}
              onClick={() => setConditions((prev) => [...prev, emptyCondition()])}
            >
              Add condition
            </Button>
          </fieldset>

          {/* Actions */}
          <fieldset className="rtk-fieldset">
            <legend className="rtk-label">Actions</legend>
            {actions.map((act, i) => (
              <ActionRow
                key={i}
                action={act}
                index={i}
                onChange={handleActionChange}
                onRemove={handleActionRemove}
              />
            ))}
            <Button
              kind="ghost"
              size="sm"
              renderIcon={Add}
              onClick={() => setActions((prev) => [...prev, emptyAction()])}
            >
              Add action
            </Button>
          </fieldset>

          <NumberInput
            id="rule-priority"
            label="Priority"
            value={priority}
            onChange={(_e, { value }: { value: string | number }) => setPriority(Number(value))}
            min={0}
            step={1}
            hideSteppers
          />

          {isEdit && onTest && (
            <Button kind="tertiary" size="sm" onClick={() => setTestModalOpen(true)}>
              Test rule
            </Button>
          )}
        </div>
      </Modal>

      {/* Test modal */}
      <Modal
        open={testModalOpen}
        modalHeading="Test rule (dry run)"
        primaryButtonText="Run test"
        secondaryButtonText="Cancel"
        primaryButtonDisabled={!testSummaryId.trim() || isNaN(parseInt(testSummaryId, 10))}
        onRequestClose={() => setTestModalOpen(false)}
        onRequestSubmit={handleTestClick}
        size="sm"
      >
        <TextInput
          id="test-summary-id"
          labelText="Summary ID"
          value={testSummaryId}
          onChange={(e) => setTestSummaryId(e.currentTarget.value)}
          placeholder="Enter a summary ID to test against"
        />
      </Modal>
    </>
  );
}
