import { ChatWorkspace } from "../components/chat/ChatWorkspace";
import { PageHeader } from "../components/ui";

export function Playground() {
  return (
    <>
      <PageHeader
        title="Playground"
        summary="Chat with a local model on Lemonade or a cloud model on your AMD endpoint. Replies stream as they are generated, with the measurements each backend reports and where the model ran."
      />
      <ChatWorkspace mode="text" />
    </>
  );
}
