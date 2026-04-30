import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react-vite";
import {
  BrutalistModal,
  ModalHeader,
  ModalBody,
  ModalFooter,
} from "./BrutalistModal";

const meta = {
  title: "Modal/BrutalistModal",
  component: BrutalistModal,
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof BrutalistModal>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    open: true,
    modalHeading: "Confirm Action",
    modalLabel: "Destructive",
    primaryButtonText: "Confirm",
    secondaryButtonText: "Cancel",
  },
  render: (args) => {
    const [open, setOpen] = useState(args.open ?? true);
    return (
      <>
        <div style={{ padding: 32 }}>
          <button type="button" onClick={() => setOpen(true)}>
            Open Modal
          </button>
        </div>
        <BrutalistModal
          {...args}
          open={open}
          onRequestClose={() => setOpen(false)}
          onRequestSubmit={() => setOpen(false)}
          onSecondarySubmit={() => setOpen(false)}
        >
          This action cannot be undone. Are you sure you want to proceed?
        </BrutalistModal>
      </>
    );
  },
};

export const SizeSmall: Story = {
  render: () => {
    const [open, setOpen] = useState(true);
    return (
      <>
        <div style={{ padding: 32 }}>
          <button type="button" onClick={() => setOpen(true)}>
            Open Compact Modal
          </button>
        </div>
        <BrutalistModal
          open={open}
          size="sm"
          modalHeading="Delete Item"
          primaryButtonText="Delete"
          secondaryButtonText="Cancel"
          danger
          onRequestClose={() => setOpen(false)}
          onRequestSubmit={() => setOpen(false)}
          onSecondarySubmit={() => setOpen(false)}
        >
          Permanently delete this item? This cannot be undone.
        </BrutalistModal>
      </>
    );
  },
};

export const SizeMedium: Story = {
  render: () => {
    const [open, setOpen] = useState(true);
    return (
      <>
        <div style={{ padding: 32 }}>
          <button type="button" onClick={() => setOpen(true)}>
            Open Content Modal
          </button>
        </div>
        <BrutalistModal
          open={open}
          size="md"
          modalHeading="Edit Configuration"
          primaryButtonText="Save"
          secondaryButtonText="Cancel"
          onRequestClose={() => setOpen(false)}
          onRequestSubmit={() => setOpen(false)}
          onSecondarySubmit={() => setOpen(false)}
        >
          <p style={{ margin: 0 }}>
            Adjust the settings below. Changes take effect immediately on save.
          </p>
        </BrutalistModal>
      </>
    );
  },
};

export const ComposedVariant: Story = {
  render: () => {
    const [open, setOpen] = useState(true);
    return (
      <>
        <div style={{ padding: 32 }}>
          <button type="button" onClick={() => setOpen(true)}>
            Open Composed Modal
          </button>
        </div>
        <BrutalistModal
          open={open}
          size="md"
          onClose={() => setOpen(false)}
        >
          <ModalHeader title="Webhook Configuration" closeModal={() => setOpen(false)} />
          <ModalBody>
            <p style={{ margin: 0, fontFamily: "var(--frost-font-mono)", fontSize: 13 }}>
              Configure the endpoint URL and authentication method.
              Changes will be validated before saving.
            </p>
          </ModalBody>
          <ModalFooter>
            <button
              type="button"
              onClick={() => setOpen(false)}
              style={{
                fontFamily: "var(--frost-font-mono)",
                fontSize: 11,
                fontWeight: 800,
                textTransform: "uppercase",
                letterSpacing: "1px",
                border: "1px solid var(--frost-ink)",
                borderRadius: 0,
                background: "var(--frost-page)",
                color: "var(--frost-ink)",
                cursor: "pointer",
                padding: "6px 12px",
              }}
            >
              [ Cancel ]
            </button>
            <button
              type="button"
              onClick={() => setOpen(false)}
              style={{
                fontFamily: "var(--frost-font-mono)",
                fontSize: 11,
                fontWeight: 800,
                textTransform: "uppercase",
                letterSpacing: "1px",
                border: "1px solid var(--frost-ink)",
                borderRadius: 0,
                background: "var(--frost-ink)",
                color: "var(--frost-page)",
                cursor: "pointer",
                padding: "6px 12px",
              }}
            >
              [ Save ]
            </button>
          </ModalFooter>
        </BrutalistModal>
      </>
    );
  },
};

export const PassiveModal: Story = {
  render: () => {
    const [open, setOpen] = useState(true);
    return (
      <>
        <div style={{ padding: 32 }}>
          <button type="button" onClick={() => setOpen(true)}>
            Open Passive Modal
          </button>
        </div>
        <BrutalistModal
          open={open}
          size="sm"
          modalHeading="Information"
          passiveModal
          onRequestClose={() => setOpen(false)}
        >
          This is a passive modal with no action buttons. Close with the × button or ESC.
        </BrutalistModal>
      </>
    );
  },
};

export const Variants: Story = {
  render: () => {
    const [activeKey, setActive] = useState<string | null>(null);
    const open = (key: string) => setActive(key);
    const close = () => setActive(null);
    return (
      <div style={{ padding: 32, display: "flex", gap: 16, flexWrap: "wrap" }}>
        <button type="button" onClick={() => open("default")}>Default (md)</button>
        <button type="button" onClick={() => open("sm")}>Confirm (sm)</button>
        <button type="button" onClick={() => open("danger")}>Danger</button>
        <button type="button" onClick={() => open("passive")}>Passive</button>

        <BrutalistModal
          open={activeKey === "default"}
          size="md"
          modalHeading="Edit Record"
          primaryButtonText="Save"
          secondaryButtonText="Cancel"
          onRequestClose={close}
          onRequestSubmit={close}
          onSecondarySubmit={close}
        >
          Content for the medium-sized modal.
        </BrutalistModal>

        <BrutalistModal
          open={activeKey === "sm"}
          size="sm"
          modalHeading="Confirm"
          primaryButtonText="Yes"
          secondaryButtonText="No"
          onRequestClose={close}
          onRequestSubmit={close}
          onSecondarySubmit={close}
        >
          Are you sure?
        </BrutalistModal>

        <BrutalistModal
          open={activeKey === "danger"}
          size="sm"
          danger
          modalHeading="Delete"
          primaryButtonText="Delete"
          secondaryButtonText="Cancel"
          onRequestClose={close}
          onRequestSubmit={close}
          onSecondarySubmit={close}
        >
          This will permanently remove the item.
        </BrutalistModal>

        <BrutalistModal
          open={activeKey === "passive"}
          size="sm"
          modalHeading="Notice"
          passiveModal
          onRequestClose={close}
        >
          No actions required. Press ESC or close.
        </BrutalistModal>
      </div>
    );
  },
};
