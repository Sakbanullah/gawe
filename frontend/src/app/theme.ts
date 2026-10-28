import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  createTheme,
  Modal,
  Paper,
  Select,
  Table,
  Tabs,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";

/**
 * Design tokens for the whole app. Everything here is Mantine theme or default
 * props, so no component needs manual CSS (UI-DESIGN.md §10).
 *
 * The palette stays calm and professional: one blue family for actions, neutral
 * greys for text, and green/orange/red only for state that also carries a label.
 */
export const theme = createTheme({
  primaryColor: "indigo",
  primaryShade: { light: 6, dark: 8 },
  fontFamily:
    "Inter, 'Segoe UI', system-ui, -apple-system, 'Helvetica Neue', Arial, sans-serif",
  fontFamilyMonospace: "'Cascadia Code', Consolas, 'Courier New', monospace",
  defaultRadius: "md",
  cursorType: "pointer",
  headings: {
    fontFamily:
      "Inter, 'Segoe UI', system-ui, -apple-system, 'Helvetica Neue', Arial, sans-serif",
    fontWeight: "600",
    sizes: {
      h1: { fontSize: "1.875rem", lineHeight: "1.25" },
      h2: { fontSize: "1.5rem", lineHeight: "1.3" },
      h3: { fontSize: "1.25rem", lineHeight: "1.35" },
      h4: { fontSize: "1.0625rem", lineHeight: "1.4" },
      h5: { fontSize: "0.9375rem", lineHeight: "1.45" },
    },
  },
  components: {
    Button: Button.extend({
      defaultProps: { size: "md", radius: "md" },
    }),
    Card: Card.extend({
      defaultProps: { withBorder: true, radius: "lg", padding: "lg" },
    }),
    Paper: Paper.extend({
      defaultProps: { radius: "lg", p: "lg" },
    }),
    TextInput: TextInput.extend({ defaultProps: { size: "md", radius: "md" } }),
    Textarea: Textarea.extend({ defaultProps: { size: "md", radius: "md" } }),
    Select: Select.extend({ defaultProps: { size: "md", radius: "md" } }),
    Checkbox: Checkbox.extend({ defaultProps: { size: "md" } }),
    Badge: Badge.extend({
      defaultProps: { radius: "sm", variant: "light", size: "md", tt: "none" },
    }),
    Alert: Alert.extend({ defaultProps: { radius: "md", variant: "light" } }),
    Table: Table.extend({
      defaultProps: {
        withTableBorder: true,
        highlightOnHover: true,
        verticalSpacing: "sm",
        horizontalSpacing: "md",
      },
    }),
    Tabs: Tabs.extend({ defaultProps: { variant: "pills", radius: "md" } }),
    Modal: Modal.extend({ defaultProps: { radius: "lg", centered: true } }),
    Title: Title.extend({ defaultProps: { c: "dark.9" } }),
  },
});
