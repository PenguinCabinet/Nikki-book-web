import TextArea from './TextArea';
import { useCollaborativeText } from './common/useCollaborativeText';

export default function TemplateEditor() {
    const sync = useCollaborativeText('/template');
    return <div id="app" className="m-3">
        <TextArea data={sync.text} setData={sync.setText}
            Do_not_edit_flag={sync.loading} setComposing={sync.setComposing} />
    </div>;
}
