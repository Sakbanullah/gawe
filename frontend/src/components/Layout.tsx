import { AppShell, Box, Burger, Divider, Drawer, Group, NavLink, Stack, Text } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { Link, Outlet, useLocation } from "react-router";

/**
 * Top navigation in plain Indonesian. The order matches the order of the work:
 * CV first, then jobs, then applications, then settings.
 */
const NAV = [
  { to: "/", label: "Beranda", description: "Langkah berikutnya" },
  { to: "/master-cv", label: "CV Utama", description: "Data dirimu" },
  { to: "/discovery", label: "Cari Lowongan", description: "Ambil lowongan baru" },
  { to: "/matches", label: "Lowongan", description: "Yang cocok untukmu" },
  { to: "/applications", label: "Lamaran Saya", description: "CV yang sedang disiapkan" },
  { to: "/settings", label: "Pengaturan", description: "Sumber dan izin" },
];

function activePath(pathname: string): string {
  if (pathname.startsWith("/applications")) return "/applications";
  return pathname;
}

export function Layout() {
  const location = useLocation();
  const [opened, { open, close }] = useDisclosure(false);
  const current = activePath(location.pathname);

  return (
    <AppShell header={{ height: { base: 60, md: 68 } }} padding={{ base: "md", md: "xl" }}>
      <AppShell.Header>
        <Group h="100%" px={{ base: "md", md: "xl" }} justify="space-between" wrap="nowrap">
          <Group gap="xs" wrap="nowrap">
            <Burger opened={opened} onClick={open} hiddenFrom="md" size="sm" aria-label="Buka menu" />
            <Text
              component={Link}
              to="/"
              fw={700}
              fz="lg"
              c="dark.9"
              style={{ textDecoration: "none" }}
            >
              Gawe
            </Text>
          </Group>

          <Group gap={4} visibleFrom="md" wrap="nowrap">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                component={Link}
                to={item.to}
                label={item.label}
                active={current === item.to}
                variant="subtle"
                style={{ borderRadius: 8, width: "auto" }}
                px="sm"
                py={6}
              />
            ))}
          </Group>

          <Box visibleFrom="md" w={48} />
        </Group>
      </AppShell.Header>

      <Drawer opened={opened} onClose={close} title="Menu" size="xs" padding="md">
        <Stack gap={2}>
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              component={Link}
              to={item.to}
              label={item.label}
              description={item.description}
              active={current === item.to}
              onClick={close}
              style={{ borderRadius: 8 }}
            />
          ))}
        </Stack>
        <Divider my="md" />
        <Text size="xs" c="dimmed">
          Gawe berjalan di komputer ini. Lamaran tetap kamu kirim sendiri di situs perusahaan.
        </Text>
      </Drawer>

      <AppShell.Main>
        <Box maw={1080} mx="auto">
          <Outlet />
        </Box>
      </AppShell.Main>
    </AppShell>
  );
}
