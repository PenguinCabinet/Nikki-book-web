import { useState } from 'react';
import Button from 'react-bootstrap/Button';
import Nav from 'react-bootstrap/Nav';
import Tabs from 'react-bootstrap/Tabs';
import Tab from 'react-bootstrap/Tab';
import FloatingLabel from 'react-bootstrap/FloatingLabel';
import Form from 'react-bootstrap/Form';
import 'bootstrap/dist/css/bootstrap.min.css';

function TextArea(props: any) {
    const data = props.data;
    const setData = props.setData;
    const Do_not_edit_flag = props.Do_not_edit_flag;

    return (
        Do_not_edit_flag == false ?
            <Form.Control as="textarea"
                value={data}
                onChange={(e: any) => setData(e.target.value)}
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
