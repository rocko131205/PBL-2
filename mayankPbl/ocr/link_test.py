import streamlit as st
st.query_params.update({"test": "0"})
st.markdown("<a href='/?test=1' target='_self'>CLICK ME</a>", unsafe_allow_html=True)
if st.query_params.get("test") == "1":
    st.success("IT WORKED!")
