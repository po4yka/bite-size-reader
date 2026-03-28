import { useState } from "react";
import {
  Button,
  ComposedModal,
  Dropdown,
  ModalBody,
  ModalFooter,
  ModalHeader,
} from "@carbon/react";
import type { DigestCategory } from "../../api/digest";

export function BatchCategoryModal({
  open,
  onClose,
  categories,
  onAssign,
  isPending,
}: {
  open: boolean;
  onClose: () => void;
  categories: DigestCategory[];
  onAssign: (categoryId: number | null) => void;
  isPending: boolean;
}) {
  const [selected, setSelected] = useState<{ id: number | null; label: string } | null>(null);

  const items = [
    { id: null as number | null, label: "No category" },
    ...categories.map((c) => ({ id: c.id as number | null, label: c.name })),
  ];

  return (
    <ComposedModal open={open} onClose={onClose}>
      <ModalHeader title="Set Category" />
      <ModalBody>
        <Dropdown
          id="batch-category-dropdown"
          titleText="Category"
          label="Select a category"
          items={items}
          itemToString={(item) => item?.label ?? ""}
          onChange={({ selectedItem }) => setSelected(selectedItem ?? null)}
        />
      </ModalBody>
      <ModalFooter>
        <Button kind="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button
          kind="primary"
          disabled={selected === null || isPending}
          onClick={() => {
            if (selected !== null) {
              onAssign(selected.id);
            }
          }}
        >
          Apply
        </Button>
      </ModalFooter>
    </ComposedModal>
  );
}
