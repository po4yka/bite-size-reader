import type { Meta, StoryObj } from "@storybook/react-vite";
import { FileUploader } from "./FileUploader";

const meta = {
  title: "Primitives/FileUploader",
  component: FileUploader,
  parameters: { layout: "padded", viewport: { defaultViewport: "frostMobile" } },
} satisfies Meta<typeof FileUploader>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    labelTitle: "Upload file",
    labelDescription: "Max file size is 10MB",
    buttonLabel: "Choose file",
  },
};

export const Variants: Story = {
  render: () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
      <FileUploader
        labelTitle="Single file"
        labelDescription="Supported formats: PDF, DOCX"
        buttonLabel="Add file"
      />
      <FileUploader
        labelTitle="Multiple files"
        labelDescription="Upload one or more files"
        buttonLabel="Add files"
        multiple
        accept={[".json", ".csv"]}
      />
      <FileUploader
        labelTitle="Disabled uploader"
        labelDescription="Uploading is currently disabled"
        buttonLabel="Choose file"
        disabled
      />
    </div>
  ),
};
