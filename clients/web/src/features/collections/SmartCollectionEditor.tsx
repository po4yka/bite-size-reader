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
  Add,
  TrashCan,
} from "../../design";

// ---------------------------------------------------------------------------
// Condition type / operator definitions for smart collections
// ---------------------------------------------------------------------------

export const SMART_CONDITION_TYPES = [
  "domain_matches",
  "title_contains",
  "has_tag",
  "language_is",
  "reading_time",
  "source_type",
  "content_contains",
] as const;

const SMART_CONDITION_OPERATORS: Record<string, string[]> = {
  domain_matches: ["equals", "contains"],
  title_contains: ["contains", "equals"],
  has_tag: ["equals", "in"],
  language_is: ["equals"],
  reading_time: ["gt", "lt", "eq", "gte", "lte"],
  source_type: ["equals"],
  content_contains: ["contains"],
};

const NUMERIC_SMART_TYPES = new Set(["reading_time"]);

export interface SmartCondition {
  type: string;
  operator: string;
  value: unknown;
}

// ---------------------------------------------------------------------------
// Sub-component: single condition row
// ---------------------------------------------------------------------------

function SmartConditionRow({
  condition,
  index,
  onChange,
  onRemove,
}: {
  condition: SmartCondition;
  index: number;
  onChange: (index: number, updated: SmartCondition) => void;
  onRemove: (index: number) => void;
}) {
  const operators = SMART_CONDITION_OPERATORS[condition.type] ?? ["equals"];
  const isNumeric = NUMERIC_SMART_TYPES.has(condition.type);

  return (
    <div style={{ display: "flex", gap: "0.5rem", alignItems: "flex-end", marginBottom: "0.5rem" }}>
      <Select
        id={`smart-cond-type-${index}`}
        labelText="Type"
        value={condition.type}
        onChange={(e) => {
          const newType = e.target.value;
          const newOps = SMART_CONDITION_OPERATORS[newType] ?? ["equals"];
          onChange(index, { type: newType, operator: newOps[0], value: "" });
        }}
      >
        {SMART_CONDITION_TYPES.map((t) => (
          <SelectItem key={t} value={t} text={t} />
        ))}
      </Select>
      <Select
        id={`smart-cond-op-${index}`}
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
          id={`smart-cond-val-${index}`}
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
          id={`smart-cond-val-${index}`}
          labelText="Value"
          value={String(condition.value ?? "")}
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

// ---------------------------------------------------------------------------
// Main editor modal
// ---------------------------------------------------------------------------

function emptyCondition(): SmartCondition {
  return { type: SMART_CONDITION_TYPES[0], operator: "equals", value: "" };
}

interface SmartCollectionEditorProps {
  open: boolean;
  onClose: () => void;
  onSave: (data: { name: string; conditions: SmartCondition[]; matchMode: "all" | "any" }) => void;
  initialData?: { name: string; conditions: SmartCondition[]; matchMode: "all" | "any" };
  isSaving?: boolean;
}

export default function SmartCollectionEditor({
  open,
  onClose,
  onSave,
  initialData,
  isSaving = false,
}: SmartCollectionEditorProps) {
  const isEdit = initialData != null;

  const [name, setName] = useState(initialData?.name ?? "");
  const [matchMode, setMatchMode] = useState<"all" | "any">(initialData?.matchMode ?? "all");
  const [conditions, setConditions] = useState<SmartCondition[]>(
    initialData?.conditions?.length ? initialData.conditions : [emptyCondition()],
  );

  function handleConditionChange(index: number, updated: SmartCondition) {
    setConditions((prev) => prev.map((c, i) => (i === index ? updated : c)));
  }

  function handleConditionRemove(index: number) {
    setConditions((prev) => prev.filter((_, i) => i !== index));
  }

  function handleSubmit() {
    onSave({ name: name.trim(), conditions, matchMode });
  }

  const canSave = name.trim().length > 0 && conditions.length > 0 && !isSaving;

  return (
    <Modal
      open={open}
      modalHeading={isEdit ? "Edit smart collection" : "Create smart collection"}
      primaryButtonText={isSaving ? "Saving..." : "Save"}
      secondaryButtonText="Cancel"
      primaryButtonDisabled={!canSave}
      onRequestClose={() => {
        if (!isSaving) onClose();
      }}
      onRequestSubmit={handleSubmit}
      size="md"
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <TextInput
          id="smart-collection-name"
          labelText="Collection name"
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
          placeholder="My smart collection"
        />

        <RadioButtonGroup
          legendText="Match mode"
          name="smart-match-mode"
          valueSelected={matchMode}
          onChange={(value) => setMatchMode(value as "all" | "any")}
        >
          <RadioButton labelText="All conditions" value="all" id="smart-match-all" />
          <RadioButton labelText="Any condition" value="any" id="smart-match-any" />
        </RadioButtonGroup>

        <fieldset className="rtk-fieldset">
          <legend className="rtk-label">Conditions</legend>
          {conditions.map((cond, i) => (
            <SmartConditionRow
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
      </div>
    </Modal>
  );
}
