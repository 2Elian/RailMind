from typing import List, Dict, Any, Optional
import pandas as pd
import numpy as np
import uuid
import json
import asyncio

from railmind.operators.llm.llm_cli import OpenAIClient, Tokenizer, RPM, TPM
from railmind.operators.model.qa_generator_model import TrainInfo, OutputSchema
from railmind.operators.templates.qa_generator import GEN_PROMPT

class QaGenerater:
    def __init__(self, model_path, model_name, url, api_key, data_path):
        self.tokenizer_instance = Tokenizer(model_path)
        self.llm_client = OpenAIClient(
                model=model_name,
                base_url=url,
                api_key=api_key,
                request_limit=True,
                rpm=RPM(1000),
                tpm=TPM(50000),
                tokenizer=self.tokenizer_instance,
            )
        self.data_path = data_path

        self.df = self._extract_excel_data()

    def _extract_excel_data(self) -> pd.DataFrame:
        try:
            df = pd.read_excel(self.data_path, dtype=str)
            df = df.fillna("")
            return df
        except Exception as e:
            print(f"读取 Excel 出错: {e}")

    def _extract_context(self, row: pd.Series) -> TrainInfo:
        return TrainInfo(
            train_no=row.get("train_no", ""),
            start_station=row.get("start_station", ""),
            end_station=row.get("end_station", ""),
            arrival_time=row.get("arrival_time", ""),
            departure_time=row.get("departure_time", ""),
            waiting_hall=row.get("waiting_hall", ""),
            ticket_gate=row.get("ticket_gate", ""),
            platform=row.get("platform", "")
        )

    async def call_llm(self, usr_prompt: str, question_type: str, source_rows: List[int]) -> List[OutputSchema]:
        final_result_str = await self.llm_client.generate_answer(usr_prompt)
        print(final_result_str)
        try:
            final_result = json.loads(final_result_str)
        except json.JSONDecodeError as e:
            print("JSON 解析失败:", e)
            return []

        outputs = []
        for item in final_result:
            outputs.append(OutputSchema(
                id=str(uuid.uuid4()),
                question=item.get("question", ""),
                answer=item.get("answer", ""),
                source_rows=source_rows,
                question_type=question_type
            ))
        return outputs

    async def generate(
        self,
        qa_type: str,
        output_json_path: str,
        n_samples: int = 200,
        k_multi_row: int = 10
    ) -> List[OutputSchema]:
        outputs: List[OutputSchema] = []
        for _ in range(n_samples):
            if qa_type in ["TYPE1", "TYPE2"]:
                sample_row_id = int(np.random.randint(0, len(self.df)))
                row = self.df.iloc[sample_row_id]
                train_info = self._extract_context(row)

                usr_prompt = GEN_PROMPT[qa_type].format(
                    train_no=train_info.train_no,
                    start_station=train_info.start_station,
                    end_station=train_info.end_station,
                    arrival_time=train_info.arrival_time,
                    departure_time=train_info.departure_time,
                    waiting_hall=train_info.waiting_hall,
                    ticket_gate=train_info.ticket_gate,
                    platform=train_info.platform
                )

                llm_out = await self.call_llm(
                    usr_prompt,
                    qa_type.lower(),
                    [sample_row_id]        # source rows
                )
                outputs.extend(llm_out)
                self._append_json(output_json_path, llm_out)
            elif qa_type == "TYPE3":
                sampled_df = self.df.sample(n=k_multi_row)
                source_rows = list(sampled_df.index.values)

                table_text = sampled_df.to_csv(sep="\t", index=False)
                usr_prompt = GEN_PROMPT["TYPE3"].format(table=table_text)

                llm_out = await self.call_llm(
                    usr_prompt,
                    "type3",
                    source_rows
                )
                outputs.extend(llm_out)
                self._append_json(output_json_path, llm_out)

            else:
                raise ValueError(f"未知 qa_type: {qa_type}")

        return outputs

    def _append_json(self, output_path: str, new_items: List[OutputSchema]):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = []
        for item in new_items:
            data.append(item.__dict__)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    async def type1_test(self) -> List[OutputSchema]:
        """
        TYPE1 单字段 QA 测试示例
        """
        row = self.df.iloc[0]
        train_info = self._extract_context(row)
        usr_prompt = GEN_PROMPT["TYPE1"].format(
            train_no=train_info.train_no,
            start_station=train_info.start_station,
            end_station=train_info.end_station,
            arrival_time=train_info.arrival_time,
            departure_time=train_info.departure_time,
            waiting_hall=train_info.waiting_hall,
            ticket_gate=train_info.ticket_gate,
            platform=train_info.platform
        )
        return await self.call_llm(usr_prompt, 'type1', [1])
    
    async def type2_test(self) -> List[OutputSchema]:
        """
        TYPE1 单字段 QA 测试示例
        """
        row = self.df.iloc[0]
        train_info = self._extract_context(row)
        usr_prompt = GEN_PROMPT["TYPE2"].format(
            train_no=train_info.train_no,
            start_station=train_info.start_station,
            end_station=train_info.end_station,
            arrival_time=train_info.arrival_time,
            departure_time=train_info.departure_time,
            waiting_hall=train_info.waiting_hall,
            ticket_gate=train_info.ticket_gate,
            platform=train_info.platform
        )
        return await self.call_llm(usr_prompt, 'type1', [1])
    
    async def type3_test(self, k: int = 10) -> List[OutputSchema]:
        """
        TYPE3 多行过滤单意图 QA 测试
        """
        sampled_df = self.df.sample(n=k)
        table_text = sampled_df.to_csv(sep="\t", index=False)
        usr_prompt = GEN_PROMPT["TYPE3"].format(table=table_text)
        print('---------------------------------Prompt---------------------------------')
        print(usr_prompt)
        return await self.call_llm(usr_prompt, 'type3', [1,2])
    
if __name__ == "__main__":
    import asyncio

    generator = QaGenerater(
        model_path="/data1/nuist_llm/TrainLLM/ModelCkpt/qwen3-30b-a3b",
        model_name="qwen30b",
        url="http://172.16.107.15:23333/v1",
        api_key="NuistMathAutoModelForCausalLM",
        data_path="/data/lzm/AgentDev/RailMind/data/raw_data.xlsx"
    )

    async def main():
        type1 = await generator.generate(
                        qa_type="TYPE1",
                        output_json_path="/data/lzm/AgentDev/RailMind/data/qa.json",
                        n_samples=200,
                        k_multi_row=10
                    )
        type2 = await generator.generate(
                        qa_type="TYPE2",
                        output_json_path="/data/lzm/AgentDev/RailMind/data/qa.json",
                        n_samples=200,
                        k_multi_row=10
                    )
        type3 = await generator.generate(
                        qa_type="TYPE3",
                        output_json_path="/data/lzm/AgentDev/RailMind/data/qa.json",
                        n_samples=200,
                        k_multi_row=10
                    )

    asyncio.run(main())