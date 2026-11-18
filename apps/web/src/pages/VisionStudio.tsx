import { ChatWorkspace } from "../components/chat/ChatWorkspace";
import { PageHeader } from "../components/ui";

export function VisionStudio() {
  return (
    <>
      <PageHeader
        title="Vision"
        summary="Ask a vision-language model, local or cloud, about an image. Small models misread text and fine detail often, so check answers that matter."
      />
      <ChatWorkspace mode="vision" />
    </>
  );
}
