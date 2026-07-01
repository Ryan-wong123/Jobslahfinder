import { RoleDetailPanel } from "@/components/RoleDetailPanel";

type RoleRoadmapPageProps = {
  params: Promise<{
    slug: string;
  }>;
};

export default async function RoleRoadmapPage({ params }: RoleRoadmapPageProps) {
  const { slug } = await params;

  return <RoleDetailPanel slug={slug} />;
}
