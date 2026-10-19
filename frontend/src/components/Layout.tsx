import { AppShell, Button, Group, Text, Title } from "@mantine/core";
import { Link, Outlet, useLocation } from "react-router";

const NAV = [
  { to: "/", label: "Overview" },
  { to: "/master-cv", label: "Master CV" },
  { to: "/discovery", label: "Discovery" },
  { to: "/matches", label: "Job Matches" },
  { to: "/applications", label: "Applications" },
  { to: "/settings", label: "Settings" },
];

export function Layout() {
  const location = useLocation();
  return (
    <AppShell header={{ height: 60 }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Title order={3}>Gawe</Title>
          <Group gap="xs">
            {NAV.map((item) => (
              <Button
                key={item.to}
                component={Link}
                to={item.to}
                variant={location.pathname === item.to ? "light" : "subtle"}
                size="compact-sm"
              >
                {item.label}
              </Button>
            ))}
          </Group>
          <Text size="sm" c="dimmed">
            lokal
          </Text>
        </Group>
      </AppShell.Header>
      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
