import type { Preview, Decorator } from "@storybook/react-vite";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

import "../src/design/index";
import "../src/styles.css";

export const globalTypes = {
  theme: {
    name: "Theme",
    defaultValue: "light",
    toolbar: {
      icon: "circlehollow",
      items: ["light", "dark"],
      dynamicTitle: true,
    },
  },
};

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

const withThemeAndProvider: Decorator = (Story, ctx) => {
  const theme = (ctx.globals as { theme?: string }).theme ?? "light";
  return (
    <QueryClientProvider client={queryClient}>
      <div
        data-theme={theme}
        style={{
          padding: 32,
          background: "var(--frost-page)",
          minHeight: "100vh",
        }}
      >
        <Story />
      </div>
    </QueryClientProvider>
  );
};

const preview: Preview = {
  decorators: [withThemeAndProvider],
  parameters: {
    layout: "fullscreen",
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
  },
};

export default preview;
