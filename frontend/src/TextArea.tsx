import Form from 'react-bootstrap/Form';
import 'bootstrap/dist/css/bootstrap.min.css';

function TextArea(props: {
    data: string;
    setData: (value: string) => void;
    Do_not_edit_flag: boolean;
    setComposing?: (active: boolean) => void;
}) {
    const data = props.data;
    const setData = props.setData;
    const Do_not_edit_flag = props.Do_not_edit_flag;

    return (
        Do_not_edit_flag == false ?
            <Form.Control as="textarea"
                value={data}
                onChange={(e) => setData(e.target.value)}
                onCompositionStart={() => props.setComposing?.(true)}
                onCompositionEnd={(e) => {
                    setData(e.currentTarget.value);
                    props.setComposing?.(false);
                }}
                    style={{fontFamily:"'Noto Sans JP', serif;",height: "calc((100vh - 42px - 110px - 40px) )"}}
            /> :
            <Form.Control as="textarea"
                value={"Now Loading..."}
                disabled
                readOnly
                    style={{fontFamily:"'Noto Sans JP', serif;",height: "calc((100vh - 42px - 110px - 40px) )"}}
            />

    )
}

export default TextArea
