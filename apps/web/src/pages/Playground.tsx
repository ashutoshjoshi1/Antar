import { ChatWorkspace } from "../components/chat/ChatWorkspace";
import { PageHeader } from "../components/ui";

export function Playground() {
  return (
    <>
      <PageHeader
        title="Playground"
        summary="Chat with a model running on your local Lemonade server. Replies stream as they are generated, with the measurements Lemonade reports for each one."
      />
      <ChatWorkspace mode="text" />
    </>
  );
}
