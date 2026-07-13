import { useState } from "react";
import { Stack, TextField } from "@fluentui/react";
import { Button } from "@fluentui/react-components";
import { Search24Regular } from "@fluentui/react-icons";

import styles from "./SearchBar.module.css";

interface Props {
    onSend: (search: string) => void;
    disabled: boolean;
    placeholder?: string;
    clearOnSend?: boolean;
}

export const SearchBar = ({ onSend, disabled, placeholder, clearOnSend }: Props) => {
    const [search, setSearch] = useState<string>("");

    const sendSearch = () => {
        if (disabled || !search.trim()) {
            return;
        }

        onSend(search);

        if (clearOnSend) {
            setSearch("");
        }
    };

    const onEnterPress = (ev: React.KeyboardEvent<Element>) => {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            sendSearch();
        }
    };

    const onSearchChange = (_ev: React.FormEvent<HTMLInputElement | HTMLTextAreaElement>, newValue?: string) => {
        if (!newValue) {
            setSearch("");
        } else if (newValue.length <= 1000) {
            setSearch(newValue);
        }
    };

    placeholder = "Enter a search term..."

    return (
        <Stack horizontal className={styles.searchBarContainer}>
            <TextField
                className={styles.searchBarTextArea}
                placeholder={placeholder}
                multiline
                resizable={false}
                borderless
                value={search}
                onChange={onSearchChange}
                onKeyDown={onEnterPress}
            />
            <div className={styles.searchBarButtonsContainer}>
                <Button
                    appearance="primary"
                    className={styles.searchButton}
                    size="large"
                    icon={<Search24Regular />}
                    onClick={sendSearch}
                >
                    Search
                </Button>
            </div>
        </Stack>
    );
};